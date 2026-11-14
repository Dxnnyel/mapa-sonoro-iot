"""
Mapa Sonoro del Campus - Receptor (Momento 3)

Recibe registros LAeq por HTTP POST, los valida contra el contrato de la
Tabla 1 (version 1, o version 2 con el campo secuencia), los guarda en
SQLite, aplica las reglas de reglas.py y muestra el mapa por zona.

Ejecutar:  python receptor.py        (escucha en http://0.0.0.0:5000)
"""
import json
import sqlite3
import threading
import time
from datetime import datetime, timezone, timedelta

from flask import Flask, jsonify, request, Response

BOGOTA = timezone(timedelta(hours=-5))
DB_PATH = "mapa_sonoro.db"

# ---------------------------------------------------------------- contrato
CAMPOS_V1 = ["equipo", "zona", "variable", "valor", "unidad", "momento",
             "ventana_s", "estado", "calidad", "version"]
CAMPOS_V2 = CAMPOS_V1 + ["secuencia"]       # version 2: numero de secuencia
ZONAS = ["biblioteca", "cafeteria", "teatrino", "circulacion", "recreativa"]
CALIDADES = ["calibrado_campo", "sin_calibrar", "simulado"]
VALOR_MIN, VALOR_MAX = 0.0, 130.0          # fuera de esto: imposible
VENTANA_S = 10

# ------------------------------------------------------------- seguridad
# Token propio por nodo (correccion del Momento 2). En un despliegue real
# viven en un archivo fuera del repositorio; aqui se cargan de tokens.json.
try:
    with open("tokens.json", encoding="utf-8") as f:
        TOKENS = json.load(f)
except FileNotFoundError:
    TOKENS = {}

# ------------------------------------------------------- regla de decision
from reglas import (UMBRAL_ENCENDER, UMBRAL_APAGAR, BAJO_SOSPECHOSO,
                    VENTANAS_DECISION, MIN_VENTANAS, ANTIGUEDAD_MAX_S,
                    SIN_DATO_S, histeresis, congelado)
EN_ALERTA = {}             # memoria de la histeresis por zona

app = Flask(__name__)
_lock = threading.RLock()


# ----------------------------------------------------------------- base de datos
def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS lecturas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recibido TEXT, equipo TEXT, zona TEXT, valor REAL,
            momento TEXT, estado TEXT, calidad TEXT, nivel TEXT,
            secuencia INTEGER, crudo TEXT);
        CREATE TABLE IF NOT EXISTS telemetria (
            equipo TEXT PRIMARY KEY, ultima_secuencia INTEGER,
            recibidos INTEGER, duplicados INTEGER, perdidos INTEGER);
        CREATE TABLE IF NOT EXISTS rechazos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recibido TEXT, ip TEXT, motivo TEXT, crudo TEXT);
        CREATE TABLE IF NOT EXISTS alertas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            momento TEXT, zona TEXT, tipo TEXT, promedio REAL, mensaje TEXT);
        """)


def ahora():
    return datetime.now(BOGOTA)


def ahora_txt():
    return ahora().isoformat(timespec="seconds")


# --------------------------------------------------------------- validacion
def validar(reg, token):
    """Devuelve (ok, motivo). Corre ANTES de guardar nada."""
    if not isinstance(reg, dict):
        return False, "el cuerpo no es un objeto JSON"
    version = reg.get("version")
    if version not in (1, 2):
        return False, f"version {version} no soportada (se espera 1 o 2)"
    campos = CAMPOS_V2 if version == 2 else CAMPOS_V1
    faltan = [c for c in campos if c not in reg]
    if faltan:
        return False, "falta el campo " + ", ".join(faltan)
    sobran = [c for c in reg if c not in campos]
    if sobran:
        return False, "campo no permitido: " + ", ".join(sobran)
    if version == 2:
        sq = reg["secuencia"]
        if isinstance(sq, bool) or not isinstance(sq, int) or sq < 0:
            return False, "secuencia debe ser un entero mayor o igual a 0"
    equipo = str(reg["equipo"])
    # Identidad + token por nodo
    if equipo not in TOKENS:
        return False, f"equipo desconocido: {equipo}"
    if token != TOKENS[equipo]:
        return False, f"token invalido para {equipo}"
    if reg["zona"] not in ZONAS:
        return False, f"zona fuera del catalogo: {reg['zona']}"
    partes = equipo.split("_")
    if len(partes) != 3 or partes[0] != "nodo" or partes[1] != reg["zona"]:
        return False, f"la zona {reg['zona']} no coincide con el equipo {equipo}"
    if reg["variable"] != "LAeq":
        return False, "variable debe ser LAeq"
    if reg["unidad"] != "dB(A)":
        return False, f"unidad {reg['unidad']} no valida (se exige dB(A))"
    if reg["ventana_s"] != VENTANA_S:
        return False, f"ventana_s debe ser {VENTANA_S}"
    if reg["estado"] not in ("ok", "error"):
        return False, "estado debe ser ok o error"
    if reg["calidad"] not in CALIDADES:
        return False, f"calidad no valida: {reg['calidad']}"
    v = reg["valor"]
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v:
        return False, "valor no es un numero"
    if v < VALOR_MIN:
        return False, f"valor fuera de rango: {v} dB(A) es menor que 0 dB(A)"
    if v > VALOR_MAX:
        return False, f"valor fuera de rango: {v} dB(A) supera 130 dB(A)"
    try:
        m = datetime.fromisoformat(str(reg["momento"]))
    except ValueError:
        return False, "momento no es una fecha ISO 8601"
    if m.tzinfo is None:
        return False, "momento sin zona horaria"
    if m - ahora() > timedelta(seconds=60):
        return False, "momento en el futuro (reloj del nodo desfasado)"
    return True, "aceptado"


def nivel_de(valor):
    if valor < BAJO_SOSPECHOSO:
        return "alerta_bajo"
    if valor > UMBRAL_ENCENDER:
        return "alerta"
    return "normal"


def edad_s(momento_txt, t=None):
    return ((t or ahora()) - datetime.fromisoformat(momento_txt)).total_seconds()


def telemetria(con, equipo, sq, momento):
    """Idea 1: secuencia. Devuelve 'duplicado' o None y actualiza contadores."""
    fila = con.execute("SELECT * FROM telemetria WHERE equipo=?", (equipo,)).fetchone()
    if fila is None:
        con.execute("INSERT INTO telemetria VALUES(?,?,?,?,?)", (equipo, sq, 1, 0, 0))
        return None
    dup = con.execute("SELECT 1 FROM lecturas WHERE equipo=? AND secuencia=? AND momento=?",
                      (equipo, sq, momento)).fetchone()
    if dup:
        con.execute("UPDATE telemetria SET duplicados=duplicados+1 WHERE equipo=?", (equipo,))
        return "duplicado"
    ult = fila["ultima_secuencia"]
    perdidos = sq - ult - 1 if sq > ult + 1 else 0      # sq < ult: el nodo se reinicio
    con.execute("UPDATE telemetria SET ultima_secuencia=?, recibidos=recibidos+1, "
                "perdidos=perdidos+? WHERE equipo=?", (max(sq, 0), perdidos, equipo))
    return None


# --------------------------------------------------------------- decision
def estado_zonas():
    """Estado de cada zona aplicando las cinco ideas."""
    t = ahora()
    salida = []
    with db() as con:
        for z in ZONAS:
            filas = [f for f in con.execute(
                "SELECT * FROM lecturas WHERE zona=? AND estado='ok' AND nivel!='tardio' "
                "ORDER BY momento DESC, id DESC LIMIT 12", (z,)).fetchall()]
            tele = con.execute("SELECT SUM(duplicados) d, SUM(perdidos) p FROM telemetria "
                               "WHERE equipo LIKE ?", (f"nodo_{z}_%",)).fetchone()
            base = {"zona": z, "valor": None, "promedio": None, "ultimo": None,
                    "calidad": None, "equipo": None,
                    "duplicados": tele["d"] or 0, "perdidos": tele["p"] or 0}
            if not filas:
                EN_ALERTA[z] = False
                salida.append({**base, "estado": "sin_dato", "decision": "sin dato: no se decide"})
                continue
            ult = filas[0]
            base.update(valor=ult["valor"], ultimo=ult["momento"], calidad=ult["calidad"],
                        equipo=ult["equipo"])
            edad = edad_s(ult["momento"], t)
            if edad > SIN_DATO_S:                       # idea 5: estado seguro
                EN_ALERTA[z] = False
                salida.append({**base, "valor": None, "estado": "sin_dato",
                               "decision": f"sin dato hace {int(edad)} s: revisar nodo, no se decide"})
                continue
            recientes = [f for f in filas
                         if edad_s(f["momento"], t) <= VENTANAS_DECISION * VENTANA_S + 5]
            recientes = recientes[:VENTANAS_DECISION]
            prom = round(sum(f["valor"] for f in recientes) / len(recientes), 1)
            base["promedio"] = prom
            if congelado([f["valor"] for f in filas]):  # idea 2: anomalia
                est, dec = "sospechoso", (f"valor congelado ({ult['valor']} dB(A) 6 veces): "
                                          "investigar, no se decide")
            elif len(recientes) < MIN_VENTANAS:
                est, dec = "observando", "pocas ventanas: aun no se decide"
            elif prom < BAJO_SOSPECHOSO:
                est, dec = "sospechoso", "nivel bajo sostenido: revisar si el sensor esta tapado"
            else:                                       # ideas 3 y 4: umbral + histeresis
                with _lock:
                    EN_ALERTA[z] = histeresis(EN_ALERTA.get(z, False), prom)
                    alerta = EN_ALERTA[z]
                if alerta:
                    est = "alerta"
                    dec = (f"ALERTA: promedio {prom} dB(A) > {UMBRAL_ENCENDER:.0f}. Aviso a Bienestar"
                           if prom > UMBRAL_ENCENDER else
                           f"sigue en ALERTA: {prom} dB(A) no ha bajado de {UMBRAL_APAGAR:.0f}")
                else:
                    est, dec = "normal", "normal: sin accion"
            salida.append({**base, "estado": est, "decision": dec})
    return salida


def vigilante():
    """Cada 5 s revisa las zonas y registra como aviso cada cambio a un estado
    que pide atencion (alerta, sin dato, sospechoso) y su recuperacion."""
    MALOS = ("alerta", "sin_dato", "sospechoso")
    avisado = {}            # ultimo estado avisado por zona
    primera = True
    while True:
        try:
            for e in estado_zonas():
                z, est = e["zona"], e["estado"]
                if primera:                       # al arrancar no se avisa nada
                    avisado[z] = "normal"
                    continue
                if est in MALOS and avisado.get(z) != est:
                    tipo = est
                elif est == "normal" and avisado.get(z) in MALOS:
                    tipo = "recuperada"
                else:
                    continue
                avisado[z] = est
                with _lock, db() as con:
                    con.execute(
                        "INSERT INTO alertas(momento,zona,tipo,promedio,mensaje)"
                        " VALUES(?,?,?,?,?)",
                        (ahora_txt(), z, tipo, e["promedio"], e["decision"]))
                print(f"[DECISION] {ahora_txt()} {z}: {e['decision']}")
            primera = False
        except Exception as ex:  # el vigilante nunca debe detener el receptor
            print("[vigilante]", ex)
        time.sleep(5)


# ------------------------------------------------------------------ rutas
@app.post("/lecturas")
def recibir():
    crudo = request.get_data(as_text=True)
    token = request.headers.get("X-Token", "")
    try:
        reg = json.loads(crudo)
    except json.JSONDecodeError:
        reg, ok, motivo = None, False, "JSON mal formado"
    else:
        ok, motivo = validar(reg, token)
    with _lock, db() as con:
        if not ok:
            con.execute("INSERT INTO rechazos(recibido,ip,motivo,crudo) VALUES(?,?,?,?)",
                        (ahora_txt(), request.remote_addr, motivo, crudo[:500]))
            print(f"[RECHAZADO] {motivo}")
            codigo = 401 if "token" in motivo or "desconocido" in motivo else 400
            return jsonify({"aceptado": False, "motivo": motivo}), codigo
        sq = reg.get("secuencia")
        if sq is not None and telemetria(con, reg["equipo"], sq, reg["momento"]) == "duplicado":
            motivo = f"duplicado: secuencia {sq} de {reg['equipo']} ya recibida, no se cuenta dos veces"
            con.execute("INSERT INTO rechazos(recibido,ip,motivo,crudo) VALUES(?,?,?,?)",
                        (ahora_txt(), request.remote_addr, motivo, crudo[:500]))
            print(f"[DUPLICADO] {motivo}")
            return jsonify({"aceptado": False, "motivo": motivo}), 409
        if reg["estado"] != "ok":
            nivel = "error_nodo"
        elif edad_s(reg["momento"]) > ANTIGUEDAD_MAX_S:   # idea 5: dato viejo no decide
            nivel = "tardio"
        else:
            nivel = nivel_de(reg["valor"])
        con.execute(
            "INSERT INTO lecturas(recibido,equipo,zona,valor,momento,estado,calidad,nivel,secuencia,crudo)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            (ahora_txt(), reg["equipo"], reg["zona"], float(reg["valor"]),
             reg["momento"], reg["estado"], reg["calidad"], nivel, sq, crudo))
    extra = " (se guarda en el historial, no decide)" if nivel == "tardio" else ""
    print(f"[ACEPTADO] {reg['equipo']} sec={sq} {reg['valor']} dB(A) -> {nivel}{extra}")
    return jsonify({"aceptado": True, "nivel": nivel}), 200


@app.get("/api/estado")
def api_estado():
    return jsonify({"hora": ahora_txt(), "umbral_encender": UMBRAL_ENCENDER,
                    "umbral_apagar": UMBRAL_APAGAR, "zonas": estado_zonas()})


@app.get("/api/registro")
def api_registro():
    with db() as con:
        lec = [dict(r) for r in con.execute(
            "SELECT id,recibido,equipo,zona,valor,momento,secuencia,estado,calidad,nivel "
            "FROM lecturas ORDER BY id DESC LIMIT 15")]
        rec = [dict(r) for r in con.execute(
            "SELECT id,recibido,ip,motivo,crudo FROM rechazos ORDER BY id DESC LIMIT 10")]
        ale = [dict(r) for r in con.execute(
            "SELECT * FROM alertas ORDER BY id DESC LIMIT 10")]
        tele = [dict(r) for r in con.execute("SELECT * FROM telemetria ORDER BY equipo")]
        tot = con.execute("SELECT COUNT(*) FROM lecturas").fetchone()[0]
    return jsonify({"total_lecturas": tot, "lecturas": lec, "rechazos": rec,
                    "alertas": ale, "telemetria": tele})


@app.get("/")
def mapa():
    with open("mapa.html", encoding="utf-8") as f:
        return Response(f.read(), mimetype="text/html")


if __name__ == "__main__":
    init_db()
    threading.Thread(target=vigilante, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, debug=False)
