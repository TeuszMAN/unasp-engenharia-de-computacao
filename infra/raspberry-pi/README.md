# Raspberry Pi 400 como broker MQTT

Servidor MQTT na rede local para as próximas fases do Projeto Integrador. O ESP32 vai publicar temperatura e estado do cooler, e o logger em Python e o agente do colega vão assinar. O plano das fases está em [docs/plano-expansao.md](../../docs/plano-expansao.md).

Configurado em 27/10/2026.

## Resumo

| Item | Valor |
|---|---|
| Host | `rasp400.local` (Raspberry Pi 400, Debian 13 trixie, kernel 6.18) |
| IP na configuração | 192.168.1.214, atribuído por DHCP e sujeito a mudança |
| Broker | Mosquitto 2.0.21, pacote do Debian |
| Porta | 1883, MQTT sem TLS, em todas as interfaces |
| Acesso | só com usuário e senha (`allow_anonymous false`) |
| Usuários | `esp32`, `logger`, `colega` |
| Serviço | `mosquitto.service`, habilitado no boot |

## Arquivos desta pasta

| Arquivo | Função |
|---|---|
| `instalar-mosquitto.sh` | Roda na Pi com sudo: atualiza o sistema, instala e configura o Mosquitto e habilita o serviço |
| `verificar-mqtt.sh` | Roda no notebook: publica, assina e testa a recusa de conexões sem senha |
| `.env.example` | Modelo das credenciais. A cópia preenchida, `.env`, fica fora do git |

## O que foi feito

1. No notebook, foi criado em `~/.ssh/config` o atalho abaixo, para entrar com `ssh rasp400`:

   ```
   Host rasp400
       HostName rasp400.local
       User mateus
       IdentityFile ~/.ssh/id_ed25519
       IdentitiesOnly yes
   ```

2. As senhas dos três usuários foram geradas no notebook (`secrets.token_urlsafe(18)`) e gravadas no `.env`.
3. A lista `usuario:senha` foi enviada à Pi pela entrada padrão do SSH, para `~/mosquitto-senhas.txt` com permissão 600. Assim a senha não aparece em linha de comando nem no histórico.
4. Na Pi, `instalar-mosquitto.sh` fez o seguinte:
   - `apt-get full-upgrade`, com 21 pacotes atualizados e sem pedido de reinicialização;
   - instalação de `mosquitto` e `mosquitto-clients`;
   - criação de `/etc/mosquitto/conf.d/lan.conf`:

     ```
     listener 1883 0.0.0.0
     allow_anonymous false
     password_file /etc/mosquitto/passwd
     ```

   - gravação de `/etc/mosquitto/passwd` com as senhas convertidas em hash (`mosquitto_passwd -U`), dono `mosquitto` e permissão 600. O arquivo em texto puro é apagado com `shred`;
   - `systemctl enable` e `restart` do serviço.
5. No notebook, `mosquitto-clients` foi instalado no Ubuntu do WSL (`apt-get install mosquitto-clients`), sem broker local.

O `sudo` da Pi pede senha. Por isso o instalador é executado em um terminal interativo:

```bash
scp infra/raspberry-pi/instalar-mosquitto.sh rasp400:~
```

```bash
ssh -t rasp400 "sudo bash ~/instalar-mosquitto.sh 2>&1 | tee ~/instalar-mosquitto.log"
```

Para refazer a instalação, envie antes as senhas do `.env` (Git Bash ou WSL, na raiz do repositório):

```bash
set -a; . infra/raspberry-pi/.env; set +a; printf '%s:%s\n' "$MQTT_USER_ESP32" "$MQTT_PASS_ESP32" "$MQTT_USER_LOGGER" "$MQTT_PASS_LOGGER" "$MQTT_USER_COLEGA" "$MQTT_PASS_COLEGA" | ssh rasp400 'umask 077; cat > ~/mosquitto-senhas.txt'
```

## Como verificar

Estado do serviço na Pi:

```bash
ssh rasp400 "systemctl is-enabled mosquitto; systemctl is-active mosquitto; ss -ltn | grep 1883"
```

Saída esperada: `enabled`, `active` e uma linha `LISTEN ... 0.0.0.0:1883`.

Teste completo a partir do notebook (no PowerShell, pelo WSL):

```bash
wsl -d Ubuntu -- bash /mnt/c/Unasp-Engenharia-de-Computacao/infra/raspberry-pi/verificar-mqtt.sh 192.168.1.214
```

O script assina `teste/#` como `logger`, publica como `esp32` e tenta publicar sem usuário e com senha errada. Saída obtida em 27/10/2026:

```
$ mosquitto_sub -h 192.168.1.214 -u logger -t 'teste/#' -v -C 1 -W 15   (em segundo plano)
$ mosquitto_pub -h 192.168.1.214 -u esp32 -t teste/notebook -m "teste do notebook 2026-10-27T19:42:08-03:00"
codigo de saida: 0
codigo de saida do sub: 0
--- recebido pelo mosquitto_sub:
teste/notebook teste do notebook 2026-10-27T19:42:08-03:00

$ mosquitto_pub -h 192.168.1.214 -t teste/anonimo -m x   (sem usuário)
Connection error: Connection Refused: not authorised.
Error: The connection was refused.
codigo de saida: 5

$ mosquitto_pub -h 192.168.1.214 -u esp32 -P senha-errada -t teste/errada -m x
Connection error: Connection Refused: not authorised.
Error: The connection was refused.
codigo de saida: 5
```

O WSL, no modo de rede padrão (NAT), não resolve nomes `.local`, por isso o teste usa o IP. No Windows o nome resolve normalmente (`Resolve-DnsName rasp400.local`). Programas que rodam direto no Windows, como o logger em Python, podem usar `rasp400.local`.

## Manutenção

Trocar a senha de um usuário ou criar outro. O comando pede a senha de forma interativa, devolve o arquivo ao usuário `mosquitto` (o broker lê o arquivo depois de abrir mão do root) e reinicia o serviço para recarregá-lo:

```bash
ssh -t rasp400 "sudo mosquitto_passwd /etc/mosquitto/passwd esp32 && sudo chown mosquitto:mosquitto /etc/mosquitto/passwd && sudo systemctl restart mosquitto"
```

Depois, atualize o `.env`. Para remover um usuário, use `sudo mosquitto_passwd -D /etc/mosquitto/passwd <usuario>`.

Ver o log do broker:

```bash
ssh -t rasp400 "sudo journalctl -u mosquitto -n 50; sudo tail -n 50 /var/log/mosquitto/mosquitto.log"
```

## Como desfazer

Remover o broker e a configuração da Pi:

```bash
ssh -t rasp400 "sudo systemctl disable --now mosquitto && sudo apt-get purge -y mosquitto mosquitto-clients && sudo apt-get autoremove -y && sudo rm -rf /etc/mosquitto /var/lib/mosquitto /var/log/mosquitto"
```

Remover os clientes do WSL:

```bash
wsl -d Ubuntu -u root -- apt-get purge -y mosquitto-clients
```

Para remover o atalho SSH, apague o bloco `Host rasp400` de `~/.ssh/config`. Para remover as credenciais locais, apague `infra/raspberry-pi/.env`.

A atualização do sistema (`full-upgrade`) não tem desfazer prático. Os pacotes atualizados continuam na versão nova.

## Observações de segurança

- O tráfego na porta 1883 não é cifrado. Usuário, senha e dados passam em texto puro na rede local. Para uma rede compartilhada (a da faculdade, por exemplo), o próximo passo é um listener TLS na porta 8883.
- Não há ACL: qualquer usuário autenticado lê e escreve em qualquer tópico. Quando os tópicos estiverem definidos, vale limitar cada usuário com `acl_file`.
- A porta 1883 não deve ser encaminhada no roteador para a internet.
