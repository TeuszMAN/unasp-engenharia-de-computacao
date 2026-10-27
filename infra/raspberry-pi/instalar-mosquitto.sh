#!/usr/bin/env bash
# Atualiza a Raspberry Pi e instala o Mosquitto com listener na rede local
# e autenticação por usuário e senha (sem acesso anônimo).
#
# Pré-requisito: ~/mosquitto-senhas.txt na Pi, com linhas "usuario:senha"
# em texto puro (o README mostra como gerar a partir do .env).
# Uso, a partir do notebook:
#   scp infra/raspberry-pi/instalar-mosquitto.sh rasp400:~
#   ssh -t rasp400 "sudo bash ~/instalar-mosquitto.sh"
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Rode com sudo." >&2
  exit 1
fi

HOME_USUARIO="$(getent passwd "${SUDO_USER:-root}" | cut -d: -f6)"
SENHAS="$HOME_USUARIO/mosquitto-senhas.txt"
if [ ! -s "$SENHAS" ]; then
  echo "Arquivo de senhas não encontrado: $SENHAS" >&2
  exit 1
fi
# O arquivo em texto puro é apagado no fim, mesmo se algo falhar.
trap 'shred -u "$SENHAS" 2>/dev/null || rm -f "$SENHAS"' EXIT

export DEBIAN_FRONTEND=noninteractive
APT_OPTS=(-y -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold)

echo "== Atualizando o sistema"
apt-get update
apt-get "${APT_OPTS[@]}" full-upgrade

echo "== Instalando o Mosquitto"
apt-get "${APT_OPTS[@]}" install mosquitto mosquitto-clients

echo "== Configurando o listener"
cat > /etc/mosquitto/conf.d/lan.conf <<'EOF'
# Listener na rede local, só com usuário e senha.
listener 1883 0.0.0.0
allow_anonymous false
password_file /etc/mosquitto/passwd
EOF
chmod 644 /etc/mosquitto/conf.d/lan.conf

echo "== Gravando as senhas (hash)"
install -m 600 "$SENHAS" /etc/mosquitto/passwd
mosquitto_passwd -U /etc/mosquitto/passwd
chown mosquitto:mosquitto /etc/mosquitto/passwd
chmod 600 /etc/mosquitto/passwd

echo "== Habilitando o serviço no boot"
systemctl enable mosquitto
systemctl restart mosquitto
sleep 1

echo "== Estado"
echo "mosquitto: $(systemctl is-enabled mosquitto), $(systemctl is-active mosquitto)"
mosquitto -h 2>/dev/null | head -1 || true
ss -ltn | grep ':1883' || echo "AVISO: nada escutando na porta 1883"
cut -d: -f1 /etc/mosquitto/passwd | sed 's/^/usuario: /'
if [ -f /var/run/reboot-required ]; then
  echo "AVISO: o sistema pede reinicialização (kernel ou firmware atualizado)."
fi
echo "== Concluído"
