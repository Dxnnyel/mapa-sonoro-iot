"""
Pruebas automaticas del receptor: cada caso envia un mensaje y revisa la
respuesta y la decision. Usa una base de datos temporal, no toca mapa_sonoro.db.

  python pruebas_automaticas.py
"""
import json
import os
import tempfile
from datetime import timedelta

import receptor as R

R.DB_PATH = os.path.join(tempfile.mkdtemp(), "prueba.db")
R.init_db()
cli = R.app.test_client()
TOK = R.TOKENS
ok_total = 0
fallas = 0


def reg(zona="biblioteca", valor=52.0, sq=0, hace_s=0, **cambios):
    r = {"equipo": f"nodo_{zona}_01", "zona": zona, "variable": "LAeq", "valor": valor,
         "unidad": "dB(A)", "momento": (R.ahora() - timedelta(seconds=hace_s)).isoformat(timespec="seconds"),
         "ventana_s": 10, "estado": "ok", "calidad": "simulado", "version": 2, "secuencia": sq}
    r.update(cambios)
    return r


def enviar(r, token=None):
    eq = r.get("equipo", "")
    return cli.post("/lecturas", data=json.dumps(r),
                    headers={"X-Token": token if token is not None else TOK.get(eq, "")})


def zona(z):
    return next(x for x in R.estado_zonas() if x["zona"] == z)


def caso(nombre, cond, detalle=""):
    global ok_total, fallas
    if cond:
        ok_total += 1
        print(f"  OK    {nombre}")
    else:
        fallas += 1
        print(f"  FALLA {nombre} {detalle}")


print("Paso 2-3 · el dato viaja y se acepta")
r = enviar(reg(valor=52.3, sq=0))
caso("registro valido -> 200 aceptado", r.status_code == 200 and r.json["aceptado"])

print("Paso 6 · datos imposibles o mal formados")
r = enviar(reg(valor=300.0, sq=1));        caso("300 dB(A) -> 400", r.status_code == 400, r.json)
r = enviar(reg(valor=-5.0, sq=1));         caso("-5 dB(A) -> 400", r.status_code == 400, r.json)
x = reg(sq=1); del x["zona"]
r = enviar(x);                             caso("falta zona -> 400", r.status_code == 400, r.json)
r = enviar(reg(sq=1, unidad="dB"));        caso("unidad dB en vez de dB(A) -> 400", r.status_code == 400)
x = reg(sq=1); x["zona"] = "parqueadero"
r = enviar(x);                             caso("zona fuera del catalogo -> 400", r.status_code == 400, r.json)
r = cli.post("/lecturas", data="{malo", headers={"X-Token": "x"})
caso("JSON mal formado -> 400", r.status_code == 400)

print("Paso 7 · seguridad")
r = enviar(reg(sq=1), token="adivinado");  caso("token adivinado -> 401", r.status_code == 401)
x = reg(sq=1); x["zona"] = "cafeteria"   # el equipo sigue siendo nodo_biblioteca_01
r = enviar(x)
caso("nodo de biblioteca dice ser cafeteria -> 400", r.status_code == 400, r.json)

print("Idea 1 · telemetria (secuencia)")
r = enviar(reg(valor=51.0, sq=1));         caso("secuencia 1 aceptada", r.status_code == 200)
dup = reg(valor=50.0, sq=2)
enviar(dup)
r = enviar(dup);                           caso("mismo mensaje dos veces -> 409 duplicado", r.status_code == 409, r.status_code)
enviar(reg(valor=50.5, sq=6))              # se saltan 3, 4 y 5
tele = cli.get("/api/registro").json["telemetria"]
bib = next(t for t in tele if t["equipo"] == "nodo_biblioteca_01")
caso("salto de secuencia 2 -> 6 cuenta 3 perdidos", bib["perdidos"] == 3, bib)

print("Idea 5 · estado seguro (antiguedad)")
r = enviar(reg(zona="teatrino", valor=90.0, sq=0, hace_s=120))
caso("dato de hace 2 min -> se guarda como tardio", r.status_code == 200 and r.json["nivel"] == "tardio")
caso("ese dato viejo no decide: teatrino sin dato", zona("teatrino")["estado"] == "sin_dato")

print("Ideas 3 y 4 · umbral y histeresis")
for i, v in enumerate([70.0, 71.0, 72.0]):
    enviar(reg(zona="cafeteria", valor=v, sq=i, hace_s=20 - 10 * i))
caso("promedio 71 > 65 -> alerta", zona("cafeteria")["estado"] == "alerta", zona("cafeteria"))
R.EN_ALERTA["cafeteria"] = True
caso("promedio 63,5 (entre 62 y 65) -> sigue en alerta", R.histeresis(True, 63.5))
caso("promedio 61,9 (bajo 62) -> sale de alerta", not R.histeresis(True, 61.9))
caso("partiendo de normal, 64,9 no enciende", not R.histeresis(False, 64.9))

print("Idea 2 · anomalia (valor congelado)")
for i in range(6):
    enviar(reg(zona="recreativa", valor=58.0, sq=i, hace_s=25 - 5 * i))
z = zona("recreativa")
caso("6 valores identicos -> sospechoso, no decide", z["estado"] == "sospechoso", z)

print("Paso 6 · nodo caido")
enviar(reg(zona="circulacion", valor=57.0, sq=0, hace_s=25))
caso("ultimo dato de hace 25 s -> sin dato", zona("circulacion")["estado"] == "sin_dato")

print()
print(f"Resultado: {ok_total} pruebas OK, {fallas} fallas")
raise SystemExit(1 if fallas else 0)
