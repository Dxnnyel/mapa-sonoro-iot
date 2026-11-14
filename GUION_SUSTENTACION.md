# Guion de sustentación · Mapa Sonoro (Momento 3)

Cada integrante debe poder explicar **cualquier** paso y mostrar el sistema funcionando. Lean esto completo; son 10 minutos.

## Antes de entrar (2 minutos)

```bash
pip install flask requests
cd receptor && python receptor.py                                  # terminal 1
cd nodo_simulado && python nodo_simulado.py --zona biblioteca      # terminal 2
cd nodo_simulado && python nodo_simulado.py --zona cafeteria --modo ruido   # terminal 3
```

Abran `http://127.0.0.1:5000`. En 30 s la cafetería pasa a rojo. Ten listo también `python pruebas_automaticas.py` (20 de 20 OK).

## Paso 1 · La idea

**Digan:** "En el campus nadie sabe en qué zonas y horas el ruido impide estudiar; solo hay quejas. Medimos el ruido de cada zona cada 10 segundos y lo comparamos con 65 dB(A), el límite de la norma para instituciones educativas. Lo usa Bienestar Universitario para decidir dónde reubicar actividades o qué zona adecuar."

**Ojo:** en el Paso 1 no se nombran aparatos ni herramientas.

## Paso 2 · El dato

**Digan:** "El dato es el LAeq en dB(A) de una ventana de 10 segundos. Sale de un nodo, por ejemplo `nodo_biblioteca_01`, con un valor como 54,0 y una hora con zona horaria de Colombia. En estas pruebas es simulado, y el propio mensaje lo dice en el campo `calidad`."

**Muestren:** la terminal del nodo (cada 10 s imprime el JSON y la respuesta 200).

**Pregunta probable:** *¿Por qué dB(A)?* → Porque pondera las frecuencias como el oído humano y es la unidad de la norma, así comparamos con una referencia.

## Paso 3 · El viaje del dato

**Digan:** "El nodo arma un JSON de 11 campos y lo envía por HTTP POST a `/lecturas` con su token. El receptor lo valida **antes** de guardar: si está bien responde 200 y lo guarda en SQLite; si no, responde 400, 401 o 409 con el motivo."

**Qué corregimos:** token por nodo, campo `secuencia` (versión 2 del contrato), historial en base de datos y cola local si el receptor se cae.

**Pregunta probable:** *¿Por qué HTTP y no MQTT?* → Porque el nodo inicia el envío (está detrás de la red del campus) y en la misma respuesta sabemos si se aceptó y por qué; con pocos nodos no necesitamos un servidor de mensajes. Con muchos nodos evaluaríamos MQTT.

**Pregunta probable:** *¿Y el ESP32 real?* → No alcanza la red de la universidad (−90 dBm), así que entrega por USB a `puente_usb.py`, que hace el mismo POST.

## Paso 4 · Qué hacemos con el dato (las cinco ideas)

**Dónde se guarda:** SQLite, tablas `lecturas`, `rechazos`, `telemetria` y `alertas`.

| Idea | Una frase para decirla |
|---|---|
| 1. Telemetría | Con equipo y secuencia detectamos duplicados (se rechazan con 409) y perdidos (se cuentan). |
| 2. Anomalías | Seis valores iguales seguidos no prueban que el sensor esté dañado: la zona queda "sospechosa, investigar" y no se decide. |
| 3. Umbral | 65 dB(A), de la Resolución 627 de 2006, comparado con el promedio de un minuto, no con una lectura suelta. |
| 4. Histéresis | Entra en alerta sobre 65 y solo sale bajo 62. Con la misma serie: un límite = 6 cambios y 3 avisos; histéresis = 2 cambios y 1 aviso. |
| 5. Estado seguro | Un dato de más de 30 s se guarda pero no decide; sin datos por más de 20 s la zona queda "sin dato: no se decide". |

**Muestren:** `python prueba_histeresis.py`.

## Paso 5 · La decisión

**Digan:** "La salida es un aviso a Bienestar Universitario, no una acción automática; decide una persona. Cuando el promedio de la cafetería pasa de 65, la zona se pone roja, aparece el aviso y queda en el historial. Con el historial, Bienestar sabe en qué franjas se repite."

**Muestren:** el mapa con la cafetería en rojo.

## Paso 6 · Cuando algo falla

**Muestren en vivo (elijan uno o dos):**

```bash
python nodo_simulado.py --zona biblioteca --nn 02 --modo imposible --veces 1   # 400
python nodo_simulado.py --zona biblioteca --nn 02 --modo duplicado --veces 1   # 409
```

- Ctrl+C en la terminal de la biblioteca → a los 20 s queda gris "sin dato, no se decide".
- Ctrl+C en el receptor 30 s → el nodo dice "registro(s) en cola local" y al volver los reenvía.

**Frase clave:** "Un dato malo nunca se convierte en alerta ni se reemplaza por cero; la falta de dato no es silencio."

## Paso 7 · Seguridad y límites

**Protegemos:** no se graba audio (solo un nivel); solo un nodo con su token escribe, y solo en su zona; todo se valida antes de guardar.

**No puede hoy:** no cifra (HTTP, no HTTPS); cualquiera en la red ve el mapa; no limita mensajes; el nodo real va por USB; la calibración es contra una app de celular (±2 a 3 dB); las pruebas son con nodos simulados.

**Con más tiempo:** HTTPS, placa con antena externa, sonómetro y nodos reales una semana, login para Bienestar, límite de mensajes, MQTT si crecen los nodos.

## Si preguntan "qué corrigieron del Momento 2 y por qué"

Historial (antes solo el último valor), token (antes cualquiera podía hacerse pasar por un nodo), secuencia (duplicados y perdidos), promedio + histéresis (antes una sola lectura disparaba la alerta), antigüedad del dato, cola local y pruebas automáticas. **El porqué de todo:** que Bienestar no tome una decisión con un dato malo, repetido, viejo o falso.
