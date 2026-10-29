/*
  PI - Monitoramento de temperatura com ESP32

  Le a temperatura no DS18B20, liga o cooler (via rele) acima de ALVO + FOLGA e
  desliga abaixo de ALVO - FOLGA (controle ON/OFF com histerese), mostra tudo
  no LCD 16x2 I2C e publica os valores numa pagina web e no broker MQTT da
  Raspberry Pi. O alvo (padrao 27,5 C, ou seja, liga a 28 C e desliga a 27 C)
  e o modo podem ser mudados por MQTT, por exemplo pelo assistente Cozmo.

  A pagina "/" ja sai do ESP32 com os valores preenchidos (%TEMPC%, %TEMPF% e
  %STATUS%), para o programa de computacao grafica conseguir le-la com
  BeautifulSoup. As rotas /temperaturec, /temperaturef e /status devolvem os
  mesmos valores em texto puro.

  MQTT (publica):
    pi-temperatura/esp32/leitura  a cada leitura, retido:
        {"ts":1730000000,"temperatura_c":27.31,"cooler":true,"alvo":27.5,"modo":"auto"}
    pi-temperatura/esp32/status   online / offline (offline pelo Last Will), retido
    pi-temperatura/esp32/evento   nao retido: {"evento":"pronto","reinicio":"ligada"}
        a cada conexao ao broker, {"evento":"teste"} e {"erro":"..."}
  "ts" e o horario Unix do NTP e "temperatura_c" vale null com falha no
  sensor; "ts" vale null enquanto o NTP nao sincroniza.

  MQTT (assina) pi-temperatura/esp32/comando, texto, um comando por mensagem
  (publicar SEM retain: um comando retido seria repetido a cada reconexao):
    ALVO 26.5       temperatura desejada (10 a 40 C)
    MODO AUTO       cooler liga/desliga sozinho em volta do alvo
    MODO RESFRIAR   o mesmo, pedido pra esfriar
    MODO AQUECER    nao ha aquecedor: o cooler desliga
    MODO DESL       cooler desligado
    COOLER LIGA / COOLER DESLIGA   na mao (SERVO 0..89 liga, 90..180 desliga)
    TESTE           liga o cooler 1 s e volta ao estado anterior
    KP x / KI x     aceitos e ignorados (aqui nao tem PI)
    ?               publica a leitura na hora
  O alvo e o modo voltam ao padrao se o ESP32 reiniciar: quem manda as ordens
  deve reenviar quando ver "online" no status ou o evento "pronto".

  A linha serial e as rotas HTTP continuam iguais.

  Ligacoes:
    DS18B20 DATA -> GPIO 23 (resistor de 4,7k entre DATA e 3,3V)
    Rele IN      -> GPIO 26
    LCD SDA/SCL  -> GPIO 21 / GPIO 22

  Rede Wi-Fi e MQTT: copie include/secrets.h.example para include/secrets.h e
  preencha. O secrets.h fica fora do git.
*/

#include <Arduino.h>
#include <WiFi.h>
#include <ESPmDNS.h>
#include <PubSubClient.h>
#include <ESPAsyncWebServer.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <LiquidCrystal_I2C.h>
#include <esp_system.h>
#include <math.h>
#include <time.h>

#include "secrets.h"  // define WIFI_SSID, WIFI_PASSWORD e os dados do MQTT

#ifndef MQTT_PASSWORD
#error "Faltam os dados do MQTT no secrets.h: copie-os de secrets.h.example."
#endif

// Pinos e componentes
// Atencao: GPIO 34 a 39 sao somente entrada no ESP32 e nao acionam o rele.
constexpr uint8_t ONE_WIRE_BUS = 23;
constexpr uint8_t PINO_RELE = 26;
constexpr uint8_t RELE_LIGADO = LOW;   // Ajustar caso o modulo seja ativo em HIGH
constexpr uint8_t RELE_DESLIGADO = HIGH;

// Histerese em volta do alvo: liga acima de ALVO + FOLGA, desliga abaixo de
// ALVO - FOLGA. Com os valores padrao sao os mesmos 28 C e 27 C de antes.
constexpr float ALVO_PADRAO = 27.5f;
constexpr float FOLGA = 0.5f;
constexpr float ALVO_MIN = 10.0f;
constexpr float ALVO_MAX = 40.0f;
constexpr unsigned long INTERVALO_LEITURA_MS = 2000;
constexpr unsigned long TEMPO_MAX_WIFI_MS = 15000;

// MQTT. Com o broker fora do ar, cada tentativa pode travar o loop por ate
// uns 4 s (mDNS + conexao TCP), por isso o intervalo entre tentativas e longo.
constexpr uint16_t MQTT_PORTA = 1883;
constexpr unsigned long INTERVALO_RECONEXAO_MQTT_MS = 15000;
constexpr uint32_t TIMEOUT_MDNS_MS = 1000;
const char* const MQTT_ID_CLIENTE = "pi-temperatura-esp32";
const char* const TOPICO_LEITURA = "pi-temperatura/esp32/leitura";
const char* const TOPICO_STATUS = "pi-temperatura/esp32/status";
const char* const TOPICO_EVENTO = "pi-temperatura/esp32/evento";
const char* const TOPICO_COMANDO = "pi-temperatura/esp32/comando";
constexpr time_t HORARIO_MINIMO_VALIDO = 1700000000;  // antes disso o NTP nao sincronizou

enum Modo { AUTO, RESFRIAR, AQUECER, DESL, MANUAL };
Modo modo = AUTO;
float alvo = ALVO_PADRAO;
bool coolerManual = false;

OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);
LiquidCrystal_I2C lcd(0x27, 16, 2);
AsyncWebServer server(80);
WiFiClient clienteRede;
PubSubClient mqtt(clienteRede);

float temperaturaC = NAN;
bool coolerLigado = false;
unsigned long ultimaLeitura = 0;
unsigned long ultimaTentativaMqtt = 0;
IPAddress ipBroker;  // 0.0.0.0 enquanto nao resolvido

void publicarLeitura();

const char* nomeModo() {
  switch (modo) {
    case AUTO:     return "auto";
    case RESFRIAR: return "resfriar";
    case AQUECER:  return "aquecer";
    case DESL:     return "desl";
    default:       return "manual";
  }
}

// Por que a placa (re)iniciou. "brownout" = a tensao caiu (fonte fraca, o
// cooler puxando corrente da mesma USB); "watchdog" = travou.
const char* motivoDoReinicio() {
  switch (esp_reset_reason()) {
    case ESP_RST_POWERON:   return "ligada";
    case ESP_RST_BROWNOUT:  return "brownout";
    case ESP_RST_EXT:       return "pino EN";
    case ESP_RST_SW:        return "software";
    case ESP_RST_PANIC:     return "panico";
    case ESP_RST_INT_WDT:
    case ESP_RST_TASK_WDT:
    case ESP_RST_WDT:       return "watchdog";
    case ESP_RST_DEEPSLEEP: return "deep sleep";
    default:                return "outro";
  }
}

// Decide o cooler a partir da medida e do modo, e aciona o rele.
void decidirCooler() {
  if (!isfinite(temperaturaC)) {
    coolerLigado = false;                  // sem leitura: desliga por seguranca
  } else {
    switch (modo) {
      case DESL:
      case AQUECER:                        // sem aquecedor: parar de esfriar
        coolerLigado = false;
        break;
      case MANUAL:
        coolerLigado = coolerManual;
        break;
      default:                             // AUTO e RESFRIAR: histerese em volta do alvo
        // Entre ALVO - FOLGA e ALVO + FOLGA o estado anterior e mantido.
        if (!coolerLigado && temperaturaC > alvo + FOLGA) {
          coolerLigado = true;
        } else if (coolerLigado && temperaturaC < alvo - FOLGA) {
          coolerLigado = false;
        }
    }
  }
  digitalWrite(PINO_RELE, coolerLigado ? RELE_LIGADO : RELE_DESLIGADO);
}

void atualizarLcd() {
  lcd.clear();
  lcd.setCursor(0, 0);
  if (isfinite(temperaturaC)) {
    lcd.print("Temp: ");
    lcd.print(temperaturaC, 1);
    lcd.print(" C");
  } else {
    lcd.print("Falha no sensor");
  }
  char linha2[17];
  snprintf(linha2, sizeof(linha2), "Cooler:%-3s A%4.1f", coolerLigado ? "ON" : "OFF", alvo);
  lcd.setCursor(0, 1);
  lcd.print(linha2);
}

// Uma unica leitura alimenta o LCD, o controle e as rotas HTTP.
void atualizarTemperatura() {
  sensors.requestTemperatures();
  float leitura = sensors.getTempCByIndex(0);

  if (leitura == DEVICE_DISCONNECTED_C || !isfinite(leitura) ||
      leitura < -55.0f || leitura > 125.0f) {
    Serial.println("Falha ao ler DS18B20; desligando cooler por seguranca.");
    temperaturaC = NAN;
  } else {
    temperaturaC = leitura;
  }

  decidirCooler();
  if (isfinite(temperaturaC)) {
    Serial.printf("Temperatura: %.2f C | Cooler: %s\n",
                  temperaturaC, coolerLigado ? "LIGADO" : "DESLIGADO");
  }
  atualizarLcd();
}

// Procura a Pi pelo nome mDNS; se ela nao responder, usa o IP do secrets.h.
IPAddress resolverBroker() {
  IPAddress ip = MDNS.queryHost(MQTT_HOST_MDNS, TIMEOUT_MDNS_MS);
  if (static_cast<uint32_t>(ip) != 0) {
    return ip;
  }
  ip.fromString(MQTT_HOST_IP);
  return ip;
}

void publicarEvento(const char* json) {
  if (mqtt.connected()) {
    mqtt.publish(TOPICO_EVENTO, json);
  }
}

void testarRele() {
  publicarEvento("{\"evento\":\"teste\"}");
  digitalWrite(PINO_RELE, RELE_LIGADO);
  delay(1000);
  digitalWrite(PINO_RELE, coolerLigado ? RELE_LIGADO : RELE_DESLIGADO);
}

void tratarComando(String cmd) {
  cmd.trim();
  cmd.toUpperCase();
  if (cmd.length() == 0) {
    return;
  }
  Serial.printf("Comando MQTT: %s\n", cmd.c_str());

  bool valido = true;
  if (cmd.startsWith("ALVO ")) {
    String argumento = cmd.substring(5);
    argumento.replace(',', '.');
    char* fim = nullptr;
    float valor = strtof(argumento.c_str(), &fim);
    if (fim == argumento.c_str() || !isfinite(valor)) {
      valido = false;
    } else {
      alvo = constrain(valor, ALVO_MIN, ALVO_MAX);
    }
  } else if (cmd == "MODO AUTO") {
    modo = AUTO;
  } else if (cmd == "MODO RESFRIAR") {
    modo = RESFRIAR;
  } else if (cmd == "MODO AQUECER") {
    modo = AQUECER;
  } else if (cmd == "MODO DESL") {
    modo = DESL;
  } else if (cmd == "COOLER LIGA" || cmd == "COOLER ON") {
    modo = MANUAL;
    coolerManual = true;
  } else if (cmd == "COOLER DESLIGA" || cmd == "COOLER OFF") {
    modo = MANUAL;
    coolerManual = false;
  } else if (cmd.startsWith("SERVO ")) {   // compatibilidade com o Cozmo
    modo = MANUAL;
    coolerManual = cmd.substring(6).toInt() < 90;
  } else if (cmd.startsWith("KP ") || cmd.startsWith("KI ")) {
    // aqui nao tem PI (o cooler e liga/desliga): aceita e ignora
  } else if (cmd == "TESTE") {
    testarRele();
  } else if (cmd != "?") {
    valido = false;
  }

  if (!valido) {
    cmd.replace('"', '\'');
    cmd.replace('\\', '/');
    String erro = "{\"erro\":\"comando invalido: " + cmd + "\"}";
    publicarEvento(erro.c_str());
    return;
  }
  decidirCooler();       // a ordem vale na hora, sem esperar a proxima leitura
  atualizarLcd();
  publicarLeitura();
}

void aoReceber(char* topico, byte* dados, unsigned int tamanho) {
  char cmd[41];
  unsigned int n = tamanho < sizeof(cmd) - 1 ? tamanho : sizeof(cmd) - 1;
  memcpy(cmd, dados, n);
  cmd[n] = '\0';
  tratarComando(String(cmd));
}

void conectarMqtt() {
  if (static_cast<uint32_t>(ipBroker) == 0) {
    ipBroker = resolverBroker();
  }
  mqtt.setServer(ipBroker, MQTT_PORTA);

  // Last Will: se o ESP32 cair sem se despedir, o broker publica "offline".
  if (mqtt.connect(MQTT_ID_CLIENTE, MQTT_USER, MQTT_PASSWORD,
                   TOPICO_STATUS, 0, true, "offline")) {
    mqtt.publish(TOPICO_STATUS, "online", true);
    mqtt.subscribe(TOPICO_COMANDO);
    Serial.printf("MQTT conectado a %s\n", ipBroker.toString().c_str());

    char pronto[64];
    snprintf(pronto, sizeof(pronto), "{\"evento\":\"pronto\",\"reinicio\":\"%s\"}",
             motivoDoReinicio());
    publicarEvento(pronto);
    publicarLeitura();
  } else {
    Serial.printf("MQTT indisponivel (estado %d); controle local segue ativo.\n",
                  mqtt.state());
    ipBroker = IPAddress();  // o IP da Pi pode ter mudado: resolve de novo
  }
}

// Retida para que quem assinar depois receba na hora a ultima leitura.
void publicarLeitura() {
  if (!mqtt.connected()) {
    return;
  }

  char ts[12] = "null";
  time_t agora = time(nullptr);
  if (agora > HORARIO_MINIMO_VALIDO) {
    snprintf(ts, sizeof(ts), "%lu", static_cast<unsigned long>(agora));
  }

  char temperatura[12] = "null";
  if (isfinite(temperaturaC)) {
    snprintf(temperatura, sizeof(temperatura), "%.2f", temperaturaC);
  }

  char payload[128];
  snprintf(payload, sizeof(payload),
           "{\"ts\":%s,\"temperatura_c\":%s,\"cooler\":%s,\"alvo\":%.1f,\"modo\":\"%s\"}",
           ts, temperatura, coolerLigado ? "true" : "false", alvo, nomeModo());
  mqtt.publish(TOPICO_LEITURA, payload, true);
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

  // Horario em UTC; o NTP e o mDNS continuam tentando se o Wi-Fi voltar depois.
  configTime(0, 0, "pool.ntp.org", "a.ntp.br");
  MDNS.begin(MQTT_ID_CLIENTE);
  mqtt.setCallback(aoReceber);
  mqtt.setSocketTimeout(3);
  if (WiFi.status() == WL_CONNECTED) {
    conectarMqtt();
  }
  ultimaTentativaMqtt = millis();

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
    publicarLeitura();
  }

  if (WiFi.status() != WL_CONNECTED) {
    return;
  }
  if (mqtt.connected()) {
    mqtt.loop();
  } else if (millis() - ultimaTentativaMqtt >= INTERVALO_RECONEXAO_MQTT_MS) {
    ultimaTentativaMqtt = millis();
    conectarMqtt();
  }
}
