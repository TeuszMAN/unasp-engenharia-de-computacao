#!/usr/bin/env bash
# Verificação do broker a partir do notebook (WSL ou Linux).
# Lê as credenciais do .env ao lado do script sem exibi-las.
# Uso: bash verificar-mqtt.sh [host]   (padrão: MQTT_HOST do .env)
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
set -a; . "$DIR/.env"; set +a
SAIDA="$(mktemp)"
HOST="${1:-$MQTT_HOST}"
MSG="teste do notebook $(date -Iseconds)"

echo "\$ mosquitto_sub -h $HOST -u logger -t 'teste/#' -v -C 1 -W 15   (em segundo plano)"
mosquitto_sub -h "$HOST" -p "$MQTT_PORT" -u "$MQTT_USER_LOGGER" -P "$MQTT_PASS_LOGGER" \
  -t 'teste/#' -v -C 1 -W 15 > "$SAIDA" 2>&1 &
SUB=$!
sleep 1

echo "\$ mosquitto_pub -h $HOST -u esp32 -t teste/notebook -m \"$MSG\""
mosquitto_pub -h "$HOST" -p "$MQTT_PORT" -u "$MQTT_USER_ESP32" -P "$MQTT_PASS_ESP32" \
  -t teste/notebook -m "$MSG"
echo "codigo de saida: $?"

wait $SUB
echo "codigo de saida do sub: $?"
echo "--- recebido pelo mosquitto_sub:"
cat "$SAIDA"

echo
echo "\$ mosquitto_pub -h $HOST -t teste/anonimo -m x   (sem usuário)"
mosquitto_pub -h "$HOST" -p "$MQTT_PORT" -t teste/anonimo -m x
echo "codigo de saida: $?"

echo
echo "\$ mosquitto_pub -h $HOST -u esp32 -P senha-errada -t teste/errada -m x"
mosquitto_pub -h "$HOST" -p "$MQTT_PORT" -u esp32 -P senha-errada -t teste/errada -m x
echo "codigo de saida: $?"
