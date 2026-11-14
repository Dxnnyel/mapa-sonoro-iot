"""
Prueba de la idea 4 (histeresis) con la misma secuencia de promedios que usa
el modo «oscila» del nodo simulado. Compara un umbral unico (65 dB(A)) con
la histeresis (entra sobre 65, sale bajo 62) y cuenta los cambios de estado.

  python prueba_histeresis.py
"""
from reglas import histeresis, umbral_unico, UMBRAL_ENCENDER, UMBRAL_APAGAR

PROMEDIOS = [63.8, 65.4, 64.6, 65.9, 64.9, 66.2, 65.1, 63.0, 61.5]


def estado(b):
    return "ALERTA" if b else "normal"


u_prev, h_prev = False, False
cambios_u = cambios_h = avisos_u = avisos_h = 0
print(f"{'min':>3}  {'prom dB(A)':>10}  {'umbral unico 65':>16}  {'histeresis 65/62':>17}")
for i, p in enumerate(PROMEDIOS, 1):
    u = umbral_unico(p)
    h = histeresis(h_prev, p)
    mu = " *" if u != u_prev else "  "
    mh = " *" if h != h_prev else "  "
    cambios_u += u != u_prev
    cambios_h += h != h_prev
    avisos_u += u and not u_prev
    avisos_h += h and not h_prev
    print(f"{i:>3}  {p:>10.1f}  {estado(u):>14}{mu}  {estado(h):>15}{mh}")
    u_prev, h_prev = u, h
print()
print(f"Umbral unico ({UMBRAL_ENCENDER:.0f}):     {cambios_u} cambios de estado, {avisos_u} avisos a Bienestar")
print(f"Histeresis ({UMBRAL_ENCENDER:.0f}/{UMBRAL_APAGAR:.0f}):    {cambios_h} cambios de estado, {avisos_h} aviso a Bienestar")
print("(* = cambio de estado)")
