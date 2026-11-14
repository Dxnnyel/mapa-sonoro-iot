# Mapa Sonoro del Campus · Momento 3

Sistema IoT que mide el nivel de ruido (LAeq, dB(A), ventana de 10 s) por zona del campus UCC Montería, lo valida, lo guarda y avisa a Bienestar Universitario cuando una zona supera 65 dB(A) (Resolución 627 de 2006).

## Estructura

| Carpeta | Qué hay |
|---|---|
| `receptor/` | `receptor.py` (Flask + SQLite): valida, guarda y sirve el mapa en `http://127.0.0.1:5000`. `reglas.py`: las cinco ideas (telemetría, anomalías, umbral, histéresis, estado seguro). `tokens.json`: token por nodo (cámbienlos). `mapa.html`: vista por zona. `pruebas_automaticas.py`: 20 pruebas. `prueba_histeresis.py`: umbral único vs. histéresis. |
| `nodo_simulado/` | `nodo_simulado.py`: nodo simulado por zona (contrato v2 con `secuencia`), con modos de fallo. |
| `GUION_SUSTENTACION.md` | Qué decir y qué mostrar en cada paso. |
| `puente_usb/` | `puente_usb.py`: para el ESP32-C3 real, lee el JSON por USB y lo envía al receptor. |
| `wokwi_esp32/` | `sketch.ino` + `diagram.json`: nodo ESP32 en Wokwi (potenciómetro = sensor). |

## Cómo ejecutarlo

```bash
pip install flask requests          # + pyserial si usan el puente USB
cd receptor && python receptor.py   # terminal 1
cd nodo_simulado                    # una terminal por zona
python nodo_simulado.py --zona biblioteca
python nodo_simulado.py --zona cafeteria --modo ruido   # genera la alerta
```

Abrir `http://127.0.0.1:5000`. Tras ~30 s (3 ventanas) cada zona deja de estar en «observando».

## Pruebas

```bash
cd receptor
python pruebas_automaticas.py    # 20 casos, debe decir 20 OK, 0 fallas
python prueba_histeresis.py      # 6 cambios con un límite vs 2 con histéresis
```

Pruebas de fallo en vivo (usan el nodo de pruebas `nodo_biblioteca_02` para no ensuciar los datos del nodo 01):

```bash
cd nodo_simulado
python nodo_simulado.py --zona biblioteca --nn 02 --modo imposible  --veces 1   # 300 dB(A) -> 400
python nodo_simulado.py --zona biblioteca --nn 02 --modo sin_zona   --veces 1   # falta zona -> 400
python nodo_simulado.py --zona biblioteca --nn 02 --modo token_malo --veces 1   # token adivinado -> 401
python nodo_simulado.py --zona biblioteca --nn 02 --modo zona_ajena --veces 1   # otra zona -> 400
python nodo_simulado.py --zona biblioteca --nn 02 --modo duplicado  --veces 1   # segundo envío -> 409
python nodo_simulado.py --zona biblioteca --nn 02 --modo tardio     --veces 1   # dato de hace 2 min: se guarda, no decide
python nodo_simulado.py --zona biblioteca --nn 02 --modo salto      --veces 2   # 3 mensajes perdidos
python nodo_simulado.py --zona recreativa --modo congelado                      # valor congelado -> sospechoso
```

- **Nodo caído:** detener (Ctrl+C) el nodo de una zona → a los 20 s queda «sin dato».
- **Receptor caído:** detener `receptor.py` unos 30 s → el nodo muestra «registro(s) en cola local» y los reenvía al volver; los de más de 30 s llegan como «tardío».

## Wokwi

1. Crear un proyecto ESP32 en wokwi.com y pegar `sketch.ino` y `diagram.json`.
2. Mover el potenciómetro cambia el nivel (25–95 dB(A)); cada 10 s sale el JSON en el monitor serie.
3. Para que llegue al receptor, `RECEPTOR_URL` debe ser una URL pública (p. ej. un túnel ngrok hacia el puerto 5000). Sin ella, el nodo muestra «receptor no responde» y guarda en cola, que es la prueba de conexión caída.

## Reglas (las cinco ideas)

| Idea | Regla |
|---|---|
| Telemetría | `equipo` + `secuencia`: duplicado → 409; salto → perdidos |
| Anomalías | 6 valores idénticos seguidos → «sospechoso: investigar», no decide |
| Umbral | promedio de 1 min (6 ventanas, mínimo 3) contra 65 dB(A) (Res. 627/2006) |
| Histéresis | entra en alerta > 65, sale < 62 |
| Estado seguro | dato con más de 30 s → tardío (no decide); > 20 s sin datos → «sin dato» |

## Límites conocidos

Sin HTTPS, vista sin login, sin límite de mensajes, un mensaje viejo reenviado con un token robado no se distingue de un reinicio, nodo real por USB, calibración de un punto contra app de celular.
