"""
Reglas de decision del Mapa Sonoro, separadas del servidor para poder
probarlas solas. Aplican las cinco ideas de la actividad
«IoT · Cinco ideas para tomar mejores decisiones»:

 1. Telemetria   -> equipo + secuencia: detectar duplicados y perdidos.
 2. Anomalias    -> valor identico 6 ventanas seguidas = sospechoso (se investiga,
                    no se declara fallo ni se decide con el).
 3. Umbral       -> 65 dB(A) diurno, Resolucion 627 de 2006.
 4. Histeresis   -> la alerta se enciende sobre 65 y solo se apaga bajo 62.
 5. Estado seguro-> un dato con mas de 30 s de antiguedad no decide; sin datos
                    recientes la zona queda "sin dato" y no se avisa nada.
"""

UMBRAL_ENCENDER = 65.0     # entra en alerta si el promedio supera este valor
UMBRAL_APAGAR = 62.0       # sale de alerta solo si el promedio baja de este valor
BAJO_SOSPECHOSO = 30.0     # promedio bajo: sensor tapado o desconectado
VENTANAS_DECISION = 6      # promedio de 1 minuto (6 ventanas de 10 s)
MIN_VENTANAS = 3           # con menos, solo se observa
VENTANAS_CONGELADO = 6     # 6 valores identicos seguidos = anomalia
ANTIGUEDAD_MAX_S = 30      # dato mas viejo que esto no decide (llega tarde)
SIN_DATO_S = 20            # mas de dos ventanas sin dato = sin dato


def histeresis(en_alerta, promedio):
    """Devuelve True si la zona queda en alerta."""
    if en_alerta:
        return promedio >= UMBRAL_APAGAR
    return promedio > UMBRAL_ENCENDER


def umbral_unico(promedio):
    return promedio > UMBRAL_ENCENDER


def congelado(valores):
    """valores: los mas recientes primero."""
    return len(valores) >= VENTANAS_CONGELADO and \
        len(set(valores[:VENTANAS_CONGELADO])) == 1
