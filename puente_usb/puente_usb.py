"""
Puente USB -> HTTP (para el ESP32-C3 real mientras no alcance la red).

Lee cada linea JSON que el nodo imprime por el puerto serie, completa el
campo "momento" con el reloj del computador si viene vacio, y la envia al
receptor con el token del nodo. Si el receptor no responde, guarda la linea
en una cola y la reenvia despues.

  pip install pyserial requests
  python puente_usb.py --puerto COM5          (Windows)
  python puente_usb.py --puerto /dev/ttyACM0  (Linux)
"""
import argparse
import json
from collections import deque
from datetime import datetime, timezone, timedelta

import requests
import serial

BOGOTA = timezone(timedelta(hours=-5))
TOKENS = json.load(open("../receptor/tokens.json", encoding="utf-8"))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--puerto", required=True)
    p.add_argument("--baudios", type=int, default=115200)
    p.add_argument("--url", default="http://127.0.0.1:5000/lecturas")
    a = p.parse_args()
    cola = deque(maxlen=360)
    with serial.Serial(a.puerto, a.baudios, timeout=15) as s:
        while True:
            linea = s.readline().decode("utf-8", "ignore").strip()
            if linea.startswith("{"):
                try:
                    reg = json.loads(linea)
                except json.JSONDecodeError:
                    print("[PUENTE] linea JSON incompleta, se descarta:", linea[:80])
                    continue
                if not reg.get("momento"):
                    reg["momento"] = datetime.now(BOGOTA).isoformat(timespec="seconds")
                cola.append(reg)
            while cola:
                reg = cola[0]
                try:
                    r = requests.post(a.url, json=reg, timeout=3,
                                      headers={"X-Token": TOKENS.get(reg.get("equipo"), "")})
                except requests.RequestException:
                    print(f"[PUENTE] receptor no responde; {len(cola)} en cola")
                    break
                print(f"[PUENTE] HTTP {r.status_code}: {r.text.strip()}")
                cola.popleft()


if __name__ == "__main__":
    main()
