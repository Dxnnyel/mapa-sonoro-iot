"""
Nodo simulado del Mapa Sonoro (Momento 3).

Genera un LAeq cada 10 s con el contrato version 2 (Tabla 1 + secuencia) y lo
envia por HTTP POST al receptor con su token. Si el receptor no responde,
guarda los registros en una cola local y los reenvia cuando vuelve (no
inventa valores).

Modos:
  normal      valores dentro del rango esperado de la zona
  ruido       entre 68 y 74 dB(A): produce una alerta
  oscila      alrededor de 65 dB(A): prueba de histeresis
  congelado   siempre el mismo valor: anomalia
  imposible   300 dB(A)                      -> rechazo 400
  sin_zona    falta el campo zona             -> rechazo 400
  token_malo  token adivinado                 -> rechazo 401
  zona_ajena  nodo de una zona dice ser otra  -> rechazo 400
  duplicado   envia dos veces el mismo mensaje -> el segundo, 409
  salto       se salta 3 secuencias           -> el receptor cuenta 3 perdidos
  tardio      momento de hace 2 minutos       -> se guarda, no decide

Ejemplo:
  python nodo_simulado.py --zona cafeteria --modo ruido
  python nodo_simulado.py --zona biblioteca --modo imposible --veces 1
"""
import argparse
import json
import os
import random
import time
from collections import deque
from datetime import datetime, timezone, timedelta

import requests

BOGOTA = timezone(timedelta(hours=-5))
AQUI = os.path.dirname(os.path.abspath(__file__))
TOKENS = json.load(open(os.path.join(AQUI, "..", "receptor", "tokens.json"), encoding="utf-8"))
BASE = {"biblioteca": 52, "cafeteria": 63, "teatrino": 56,
        "circulacion": 58, "recreativa": 60}
OSCILA = [63.8, 65.4, 64.6, 65.9, 64.9, 66.2, 65.1, 63.0, 61.5]
MODOS = ["normal", "ruido", "oscila", "congelado", "imposible", "sin_zona",
         "token_malo", "zona_ajena", "duplicado", "salto", "tardio"]


def registro(zona, modo, sq, n, nn="01"):
    equipo = f"nodo_{zona}_{nn}"
    momento = datetime.now(BOGOTA)
    if modo == "ruido":
        valor = random.uniform(68, 74)
    elif modo == "oscila":
        valor = OSCILA[n % len(OSCILA)]
    elif modo == "congelado":
        valor = 58.0
    elif modo == "imposible":
        valor = 300.0
    else:
        valor = random.gauss(BASE[zona], 2.0)
    if modo == "tardio":
        momento -= timedelta(minutes=2)
    reg = {"equipo": equipo, "zona": zona, "variable": "LAeq",
           "valor": round(valor, 1), "unidad": "dB(A)",
           "momento": momento.isoformat(timespec="seconds"),
           "ventana_s": 10, "estado": "ok", "calidad": "simulado", "version": 2,
           "secuencia": sq}
    token = TOKENS.get(equipo, "")
    if modo == "sin_zona":
        del reg["zona"]
    if modo == "token_malo":
        token = "adivinado-123"
    if modo == "zona_ajena":
        reg["zona"] = "cafeteria" if zona != "cafeteria" else "biblioteca"
    return reg, token


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--zona", default="biblioteca",
                   choices=list(BASE))
    p.add_argument("--modo", default="normal", choices=MODOS)
    p.add_argument("--url", default="http://127.0.0.1:5000/lecturas")
    p.add_argument("--veces", type=int, default=0, help="0 = sin fin")
    p.add_argument("--periodo", type=float, default=10.0)
    p.add_argument("--secuencia", type=int, default=0, help="secuencia inicial")
    p.add_argument("--nn", default="01", help="numero del nodo en la zona (01, 02...)")
    a = p.parse_args()

    cola = deque(maxlen=360)   # hasta 1 hora de registros si se cae la red
    sq, n = a.secuencia, 0
    while a.veces == 0 or n < a.veces:
        if a.modo == "salto" and n == 1:
            sq += 3                            # simula 3 mensajes perdidos
        item = registro(a.zona, a.modo, sq, n, a.nn)
        cola.append(item)
        if a.modo == "duplicado":
            cola.append(item)                  # el mismo mensaje otra vez
        sq += 1
        while cola:
            reg, token = cola[0]
            try:
                r = requests.post(a.url, json=reg, headers={"X-Token": token}, timeout=3)
            except requests.RequestException:
                print(f"[NODO] receptor no responde; {len(cola)} registro(s) en cola local")
                break
            print(f"[NODO] envio {json.dumps(reg, ensure_ascii=False)}")
            print(f"[NODO] respuesta HTTP {r.status_code}: {r.text.strip()}")
            cola.popleft()     # aceptado o rechazado con motivo: no se reintenta
        n += 1
        if a.veces == 0 or n < a.veces:
            time.sleep(a.periodo)


if __name__ == "__main__":
    main()
