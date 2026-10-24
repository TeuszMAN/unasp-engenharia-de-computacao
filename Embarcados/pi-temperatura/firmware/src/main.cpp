/*
  PI - Monitoramento de temperatura com ESP32

  Le a temperatura no DS18B20, liga o cooler (via rele) acima de TEMP_LIGAR e
  desliga abaixo de TEMP_DESLIGAR (controle ON/OFF com histerese), mostra tudo
  no LCD 16x2 I2C e publica os valores numa pagina web.

  A pagina "/" ja sai do ESP32 com os valores preenchidos (%TEMPC%, %TEMPF% e
  %STATUS%), para o programa de computacao grafica conseguir le-la com
  BeautifulSoup. As rotas /temperaturec, /temperaturef e /status devolvem os
  mesmos valores em texto puro.

  Ligacoes:
    DS18B20 DATA -> GPIO 23 (resistor de 4,7k entre DATA e 3,3V)
    Rele IN      -> GPIO 26
    LCD SDA/SCL  -> GPIO 21 / GPIO 22

  Rede Wi-Fi: copie include/secrets.h.example para include/secrets.h e
  preencha. O secrets.h fica fora do git.
*/

#include <Arduino.h>
#include <WiFi.h>
#include <ESPAsyncWebServer.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <LiquidCrystal_I2C.h>
#include <math.h>

#include "secrets.h"  // define WIFI_SSID e WIFI_PASSWORD

// Pinos e componentes
// Atencao: GPIO 34 a 39 sao somente entrada no ESP32 e nao acionam o rele.
constexpr uint8_t ONE_WIRE_BUS = 23;
constexpr uint8_t PINO_RELE = 26;
constexpr uint8_t RELE_LIGADO = LOW;   // Ajustar caso o modulo seja ativo em HIGH
constexpr uint8_t RELE_DESLIGADO = HIGH;

// Limiares com histerese
constexpr float TEMP_LIGAR = 28.0f;
constexpr float TEMP_DESLIGAR = 27.0f;
constexpr unsigned long INTERVALO_LEITURA_MS = 2000;
constexpr unsigned long TEMPO_MAX_WIFI_MS = 15000;

OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);
LiquidCrystal_I2C lcd(0x27, 16, 2);
AsyncWebServer server(80);

float temperaturaC = NAN;
bool coolerLigado = false;
unsigned long ultimaLeitura = 0;

// Uma unica leitura alimenta o LCD, o controle e as rotas HTTP.
void atualizarTemperatura() {
  sensors.requestTemperatures();
  float leitura = sensors.getTempCByIndex(0);

  if (leitura == DEVICE_DISCONNECTED_C || !isfinite(leitura) ||
      leitura < -55.0f || leitura > 125.0f) {
    Serial.println("Falha ao ler DS18B20; desligando cooler por seguranca.");
    temperaturaC = NAN;
    coolerLigado = false;
    digitalWrite(PINO_RELE, RELE_DESLIGADO);
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("Falha no sensor");
    return;
  }

  temperaturaC = leitura;

  // Histerese: entre TEMP_DESLIGAR e TEMP_LIGAR o estado anterior e mantido.
  if (!coolerLigado && temperaturaC > TEMP_LIGAR) {
    coolerLigado = true;
  } else if (coolerLigado && temperaturaC < TEMP_DESLIGAR) {
    coolerLigado = false;
  }
  digitalWrite(PINO_RELE, coolerLigado ? RELE_LIGADO : RELE_DESLIGADO);

  Serial.printf("Temperatura: %.2f C | Cooler: %s\n",
                temperaturaC, coolerLigado ? "LIGADO" : "DESLIGADO");

  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Temp: ");
  lcd.print(temperaturaC, 1);
  lcd.print(" C");
  lcd.setCursor(0, 1);
  lcd.print("Cooler: ");
  lcd.print(coolerLigado ? "ON" : "OFF");
}

// Troca os placeholders da pagina pelos valores atuais antes de enviar.
String processador(const String& var) {
  if (var == "TEMPC") {
    return isfinite(temperaturaC) ? String(temperaturaC, 2) : String("--");
  }
  if (var == "TEMPF") {
    return isfinite(temperaturaC) ? String(temperaturaC * 1.8f + 32.0f, 2) : String("--");
  }
  if (var == "STATUS") {
    return coolerLigado ? String("LIGADO") : String("DESLIGADO");
  }
  return String();
}

const char paginaHTML[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html lang="pt-br">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Monitoramento ESP32</title>
  <style>
    body { font-family: Arial, sans-serif; text-align: center; padding: 30px; }
    .valor { font-size: 2em; margin: 12px; }
  </style>
</head>
<body>
  <h2>Monitoramento de Temperatura</h2>
  <p class="valor">Celsius: <span id="c">%TEMPC%</span> &deg;C</p>
  <p class="valor">Fahrenheit: <span id="f">%TEMPF%</span> &deg;F</p>
  <p class="valor">Cooler: <span id="status">%STATUS%</span></p>
  <script>
    async function atualizar() {
      try {
        const [c, f, status] = await Promise.all([
          fetch('/temperaturec'), fetch('/temperaturef'), fetch('/status')
        ]);
        if (!c.ok || !f.ok || !status.ok) throw new Error('HTTP');
        document.getElementById('c').textContent = await c.text();
        document.getElementById('f').textContent = await f.text();
        document.getElementById('status').textContent = await status.text();
      } catch (erro) {
        document.getElementById('status').textContent = 'SEM CONEXAO';
      }
    }
    setInterval(atualizar, 2000);
  </script>
</body>
</html>
)rawliteral";

void setup() {
  // Configura o estado de repouso antes de configurar como saida.
  digitalWrite(PINO_RELE, RELE_DESLIGADO);
  pinMode(PINO_RELE, OUTPUT);

  Serial.begin(115200);
  lcd.init();
  lcd.backlight();
  lcd.setCursor(0, 0);
  lcd.print("Iniciando...");
  sensors.begin();
  atualizarTemperatura();
  ultimaLeitura = millis();

  // Espera o Wi-Fi por um tempo limitado: sem rede, o controle do cooler
  // continua funcionando localmente e o ESP32 tenta reconectar sozinho.
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Conectando ao Wi-Fi");
  unsigned long inicioWifi = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - inicioWifi < TEMPO_MAX_WIFI_MS) {
    delay(500);
    Serial.print(".");
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("\nEndereco IP: ");
    Serial.println(WiFi.localIP());
    // Mostra o IP no LCD por alguns segundos (e o IP usado no programa Python).
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("IP do ESP32:");
    lcd.setCursor(0, 1);
    lcd.print(WiFi.localIP());
    delay(4000);
  } else {
    Serial.println("\nWi-Fi indisponivel; controle local segue ativo.");
  }

  server.on("/", HTTP_GET, [](AsyncWebServerRequest *request) {
    request->send(200, "text/html; charset=utf-8", paginaHTML, processador);
  });
  server.on("/temperaturec", HTTP_GET, [](AsyncWebServerRequest *request) {
    request->send(200, "text/plain", isfinite(temperaturaC) ? String(temperaturaC, 2) : "--");
  });
  server.on("/temperaturef", HTTP_GET, [](AsyncWebServerRequest *request) {
    request->send(200, "text/plain", isfinite(temperaturaC) ? String(temperaturaC * 1.8f + 32.0f, 2) : "--");
  });
  server.on("/status", HTTP_GET, [](AsyncWebServerRequest *request) {
    request->send(200, "text/plain", coolerLigado ? "LIGADO" : "DESLIGADO");
  });
  server.begin();

  atualizarTemperatura();
  ultimaLeitura = millis();
}

void loop() {
  unsigned long agora = millis();
  if (agora - ultimaLeitura >= INTERVALO_LEITURA_MS) {
    ultimaLeitura = agora;
    atualizarTemperatura();
  }
}
