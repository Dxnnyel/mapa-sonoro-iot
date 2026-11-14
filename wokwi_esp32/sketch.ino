/*
  Mapa Sonoro del Campus - Nodo ESP32 (simulacion en Wokwi, Momento 3)

  El potenciometro reemplaza al sensor de sonido: su posicion se convierte en
  un LAeq entre 25 y 95 dB(A). Cada 10 s el nodo arma el registro de la
  Tabla 1 version 2 (10 campos + secuencia), lo imprime por Serial y lo envia por HTTP POST al
  receptor con su token (cabecera X-Token).

  Respuesta segura en el nodo:
   - Si el ADC queda pegado en 0 o 4095 (sensor desconectado / saturado),
     el registro sale con estado "error" (el receptor no lo promedia).
   - Si no hay WiFi o el receptor no responde, el registro se guarda en una
     cola en RAM (max 30) y se reenvia despues. Nunca se inventa un valor.
   - Sin hora NTP no se envia nada: un registro sin "momento" no sirve.
*/
#include <WiFi.h>
#include <HTTPClient.h>
#include <time.h>

const char* WIFI_SSID = "Wokwi-GUEST";
const char* WIFI_PASS = "";
// URL publica del receptor (p. ej. un tunel ngrok hacia el computador).
const char* RECEPTOR_URL = "http://CAMBIAR-POR-URL-PUBLICA/lecturas";
const char* EQUIPO = "nodo_biblioteca_01";
const char* ZONA   = "biblioteca";
const char* TOKEN  = "cambiar-esto-bib-7f3a";

const int PIN_SENSOR = 34;
const unsigned long VENTANA_MS = 10000;
const int MAX_COLA = 30;

String cola[MAX_COLA];
int enCola = 0;
unsigned long inicioVentana = 0;
unsigned long secuencia = 0;     // idea 1: telemetria (detecta perdidos/duplicados)
double sumaCuadrados = 0;
long muestras = 0;
int crudoMin = 4095, crudoMax = 0;

String momentoISO() {
  struct tm t;
  if (!getLocalTime(&t, 100)) return "";
  char b[32];
  strftime(b, sizeof(b), "%Y-%m-%dT%H:%M:%S-05:00", &t);
  return String(b);
}

String armarRegistro(float valor, const char* estado, const String& momento) {
  String j = "{";
  j += "\"equipo\":\"" + String(EQUIPO) + "\",";
  j += "\"zona\":\"" + String(ZONA) + "\",";
  j += "\"variable\":\"LAeq\",";
  j += "\"valor\":" + String(valor, 1) + ",";
  j += "\"unidad\":\"dB(A)\",";
  j += "\"momento\":\"" + momento + "\",";
  j += "\"ventana_s\":10,";
  j += "\"estado\":\"" + String(estado) + "\",";
  j += "\"calidad\":\"simulado\",";
  j += "\"version\":2,";
  j += "\"secuencia\":" + String(secuencia) + "}";
  return j;
}

void encolar(const String& r) {
  if (enCola == MAX_COLA) {            // cola llena: se descarta el mas viejo
    for (int i = 1; i < MAX_COLA; i++) cola[i - 1] = cola[i];
    enCola--;
  }
  cola[enCola++] = r;
}

void vaciarCola() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.printf("[NODO] sin WiFi: %d registro(s) en cola\n", enCola);
    WiFi.reconnect();
    return;
  }
  while (enCola > 0) {
    HTTPClient http;
    http.begin(RECEPTOR_URL);
    http.setTimeout(3000);
    http.addHeader("Content-Type", "application/json");
    http.addHeader("X-Token", TOKEN);
    int code = http.POST(cola[0]);
    if (code <= 0) {                     // receptor caido: se reintenta luego
      Serial.printf("[NODO] receptor no responde (%d); %d en cola\n", code, enCola);
      http.end();
      return;
    }
    Serial.printf("[NODO] HTTP %d: %s\n", code, http.getString().c_str());
    http.end();
    for (int i = 1; i < enCola; i++) cola[i - 1] = cola[i];   // 200 o 4xx: sale
    enCola--;
  }
}

void setup() {
  Serial.begin(115200);
  analogReadResolution(12);
  WiFi.begin(WIFI_SSID, WIFI_PASS, 6);
  Serial.print("[NODO] conectando WiFi");
  for (int i = 0; i < 40 && WiFi.status() != WL_CONNECTED; i++) { delay(250); Serial.print("."); }
  Serial.println(WiFi.status() == WL_CONNECTED ? " ok" : " sin red (se reintenta)");
  configTime(-5 * 3600, 0, "pool.ntp.org", "time.google.com");
  inicioVentana = millis();
}

void loop() {
  // Muestreo: en el nodo real aqui va la senal del microfono filtrada con
  // ponderacion A a 8000 muestras/s. En Wokwi el potenciometro fija el nivel.
  int crudo = analogRead(PIN_SENSOR);
  crudoMin = min(crudoMin, crudo);
  crudoMax = max(crudoMax, crudo);
  double nivel = 25.0 + (crudo / 4095.0) * 70.0;        // 25..95 dB(A)
  sumaCuadrados += pow(10.0, nivel / 10.0);             // promedio energetico
  muestras++;
  delay(20);

  if (millis() - inicioVentana >= VENTANA_MS) {
    float laeq = 10.0 * log10(sumaCuadrados / muestras);
    const char* estado = "ok";
    if (crudoMax == 0 || crudoMin == 4095) estado = "error";   // pegado a un riel
    String m = momentoISO();
    if (m == "") {
      Serial.println("[NODO] sin hora NTP: no se arma registro");
    } else {
      String r = armarRegistro(laeq, estado, m);
      secuencia++;
      Serial.println(r);
      encolar(r);
      vaciarCola();
    }
    inicioVentana = millis();
    sumaCuadrados = 0; muestras = 0; crudoMin = 4095; crudoMax = 0;
  }
}
