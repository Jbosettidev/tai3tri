# Estacionamento Inteligente — ESP32 + XMPP (Prosody)

Sem banco: tudo em RAM. Arquitetura resumida em [ARQUITETURA.md](ARQUITETURA.md).

```
Painel (navegador) ⇄ HTTP/WebSocket ⇄ FastAPI + Slixmpp ⇄ XMPP ⇄ Prosody ⇄ XMPP ⇄ ESP32
```

## 1. Prosody (já instalado, 1 usuário só)
Backend e ESP32 usam **a mesma conta** (ex.: `parking@localhost`), cada um com um *resource*
(`/backend` e `/esp32`). Crie a conta uma vez:
```bash
sudo prosodyctl register parking localhost parking-pass     # usuário, domínio (VirtualHost), senha
```
O ESP32 não faz TLS, então adicione **antes** da linha `VirtualHost "..."` do `/etc/prosody/prosody.cfg.lua`:
```lua
c2s_require_encryption = false
allow_unencrypted_plain_auth = true
```
e reinicie (`sudo systemctl restart prosody`). **Só para rede local.** Libere a porta 5222 (ESP32) e 8000 (painel) na LAN.

## 2. Backend (Python)
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export XMPP_JID=parking@localhost XMPP_PASSWORD=parking-pass   # ajuste p/ sua conta (ver .env.example)
uvicorn app.main:app --host 0.0.0.0 --port 8000                # 1 worker (estado em RAM)
```
Painel: `http://IP-DO-PC:8000` — testes: `pip install pytest && pytest`.

**Sem hardware:** `python -m tools.fake_esp32` (outro terminal) simula o ESP32 pela mesma conta.

## 3. Firmware (PlatformIO)
```bash
cd firmware-esp32
cp include/secrets.h.example include/secrets.h   # Wi-Fi, IP do PC (não use localhost), conta/senha/domínio
pio run -t upload && pio device monitor          # esperado: "[xmpp] sessão estabelecida"
```
Pinos em `include/config.h` (TRIG 13/14/25/26, ECHO 34/35/32/33, LED verde 16-19, LED vermelho 21/22/23/27).
**ECHO do HC-SR04 é 5 V → divisor de tensão (1k/2k) antes do ESP32.**

## O que foi testado
- Backend + Prosody 0.12 (config padrão + as 2 linhas acima, conta única): vagas, comandos, ESP offline/online (presença XMPP),
  queda/reinício do Prosody e do backend, WebSocket, painel.
- Código REAL do firmware (`main/xmpp_client/sensores/leds`) compilado no PC com um shim do Arduino e ligado no mesmo Prosody:
  login SASL PLAIN, bind, mensagens JSON nos dois sentidos, filtro de vagas (ocupada/falha), comandos, reconexão.
- **Não testado:** compilação p/ ESP32 (`pio run`) e hardware real (sensores/LEDs/Wi-Fi). Se algo falhar, comece só pela conexão XMPP no Serial.
