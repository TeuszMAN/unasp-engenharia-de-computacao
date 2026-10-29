# Plano de expansão do Projeto Integrador

Este documento descreve as fases previstas depois da entrega de 28/10/2026 do [monitoramento de temperatura com ESP32](../Embarcados/pi-temperatura). Nenhuma delas altera a versão entregue: cada fase deve partir de uma cópia ou de um branch próprio.

## Estado atual

- O ESP32 lê o DS18B20 a cada 2 s, liga e desliga o cooler com histerese e expõe a leitura em HTTP (`/temperaturec`, `/temperaturef`, `/status`) e na serial (`Temperatura: %.2f C | Cooler: LIGADO|DESLIGADO`).
- O agente assistente de um colega lê a linha serial pelo USB. Ela é uma interface e não deve mudar sem combinar com ele. As rotas HTTP são usadas pela página web e pelo programa de computação gráfica.
- A Raspberry Pi 400 (`rasp400.local`) já roda o broker Mosquitto na porta 1883, com usuário e senha. Detalhes em [infra/raspberry-pi](../infra/raspberry-pi/README.md).
- O firmware já publica a leitura por MQTT (fase 1, publicação no ESP32), sem mudar a serial nem as rotas HTTP. O formato está no [README do projeto](../Embarcados/pi-temperatura/README.md#mqtt). Falta gravar no ESP32 e testar com a Pi ligada.

## Fase 1: telemetria por MQTT e identificação da planta

### Publicação no ESP32 (implementada)

- Resolve o broker com `MDNS.queryHost("rasp400")` e usa o IP fixo do `secrets.h` como reserva. Vale também reservar o IP da Pi no DHCP do roteador.
- Biblioteca `PubSubClient`. Credenciais do usuário `esp32` em `secrets.h`, com `secrets.h.example` versionado.
- Tópicos:

  | Tópico | Conteúdo | Retido |
  |---|---|---|
  | `pi-temperatura/esp32/leitura` | JSON `{"ts":1730000000,"temperatura_c":27.31,"cooler":true}` | sim |
  | `pi-temperatura/esp32/status` | `online` / `offline` (este último pelo Last Will) | sim |

- `ts` em segundos Unix, com o relógio do ESP32 sincronizado por NTP. Assim o carimbo de tempo não depende do atraso da rede. Sem NTP, `ts` vale `null` e o logger usa o horário de recepção.
- JSON plano, com três campos e unidade no nome: cabe numa linha, qualquer cliente lê sem esquema e o agente entende sem tabela de códigos. Falha no sensor vira `"temperatura_c":null`.
- A leitura passou a ser retida (antes estava prevista como não retida) para que o agente receba o último valor assim que assinar, sem esperar o próximo ciclo.
- Manter as rotas HTTP e a linha serial durante a transição, para o agente do colega continuar funcionando até migrar.

### Comandos para o agente (implementado no firmware)

O ESP32 também assina `pi-temperatura/esp32/comando` e aceita `ALVO`, `MODO`, `COOLER` e `TESTE`, e a leitura ganhou os campos `alvo` e `modo`. Com isso o agente muda o alvo e liga ou desliga o cooler pelo broker, sem a serial. Os comandos e o evento `pronto` estão no [README do projeto](../Embarcados/pi-temperatura/README.md#comandos). A escolha entre ON/OFF e PI da fase 2 continua prevista para `pi-temperatura/esp32/config`, sem relação com esse tópico.

### Logger em Python

- `paho-mqtt` assinando `pi-temperatura/esp32/#` com o usuário `logger`.
- Grava um CSV por ensaio: `ts,temperatura_c,cooler,pwm`. A coluna `pwm` fica vazia até a fase 2.
- Pode rodar no notebook durante os ensaios ou como serviço `systemd` na própria Pi.

### Agente do colega

- Passa a assinar `pi-temperatura/esp32/leitura` com o usuário `colega`, no lugar da leitura serial. Isso dispensa o cabo USB e libera a porta COM, que hoje só um programa por vez consegue abrir.
- Mostrar a ele o formato do JSON acima. Se ele precisar de outro campo, o firmware acrescenta sem quebrar os existentes.
- O firmware continua imprimindo a linha serial, que serve de reserva se a rede ou a Pi falharem.
- O broker só é alcançável na mesma rede da Pi. Nos ensaios na faculdade, levar a Pi e usar um roteador próprio ou o ponto de acesso do celular, já que redes institucionais costumam isolar os clientes e bloquear mDNS.

### Ensaio de degrau e modelo de 1ª ordem com atraso

- Modelo: `G(s) = K e^(-θs) / (τs + 1)`, com entrada cooler (0 ou 1, depois duty cycle) e saída temperatura.
- Procedimento: deixar a temperatura estabilizar com o cooler desligado, aplicar o degrau (cooler ligado) e registrar até um novo regime. Repetir pelo menos três vezes e no sentido inverso.
- Período de amostragem: 1 s é suficiente, já que a conversão de 12 bits do DS18B20 leva 750 ms.
- Estimativa inicial pelo método de dois pontos (instantes em que a resposta atinge 28,3% e 63,2% da variação total), refinada por mínimos quadrados (`scipy.optimize.curve_fit`) sobre o CSV.
- Como o cooler resfria, o ganho `K` é negativo. Registrar a temperatura ambiente em cada ensaio, porque ela desloca o regime.

## Fase 2: ON/OFF com histerese contra controle PI com PWM

- Cooler em PWM pelo periférico LEDC do ESP32, em um GPIO de saída (nunca 34 a 39). Para cooler de 12 V, MOSFET de nível lógico com diodo de roda livre; para cooler de 4 fios, usar o pino de PWM a 25 kHz.
- Sintonia do PI a partir de `K`, `τ` e `θ` da fase 1, por exemplo pela regra SIMC: `Kc = τ / (|K| (τc + θ))` e `Ti = min(τ, 4 (τc + θ))`, com `τc` escolhido entre `θ` e `τ`. Incluir anti-windup, porque o duty cycle satura em 0% e 100%.
- Ensaios iguais para os dois controladores: mesma referência, mesma perturbação e mesma temperatura ambiente, tanto quanto possível.
- Métricas: erro em regime, sobressinal, tempo de acomodação, IAE, amplitude da oscilação e número de comutações do cooler (desgaste) ou energia média.
- O controlador ativo e os parâmetros ficam configuráveis por MQTT (por exemplo `pi-temperatura/esp32/config`), para trocar sem regravar o firmware.

## Fase 3: carga térmica gerada por Arduino UNO

- O UNO aciona um resistor de potência por MOSFET em PWM e funciona como perturbação controlada: degraus, rampas ou um perfil repetível de carga.
- Trechos em assembly AVR: configuração do Timer1 para o PWM, rotina de interrupção que avança o perfil de carga e, se fizer sentido, a leitura de um sensor de segurança. Os trechos ficam em um arquivo `.S` chamado a partir do código C, o que permite comparar tamanho e tempo de execução com a versão em C.
- Segurança: desligamento por temperatura máxima no próprio UNO, independente do ESP32.
- Se o UNO falar com o ESP32 por serial, usar divisor de tensão ou conversor de nível, porque o UNO trabalha em 5 V e o ESP32 em 3,3 V. Outra opção é o ESP32 publicar o perfil e o UNO só executá-lo.
- Com a carga conhecida, repetir os ensaios da fase 2 medindo a rejeição de perturbação de cada controlador.
