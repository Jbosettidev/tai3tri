# Arquitetura (resumo)

**Conta única no Prosody** (`parking@localhost`): backend = resource `backend`, ESP32 = resource `esp32`.
Mensagens vão de JID completo para JID completo. Sem banco: estado, histórico (100) e log XMPP (100) em `deque`/`dict`.

## Fluxos
- **Evento:** ESP32 muda vaga → `<message>` JSON → Prosody → Slixmpp → valida → atualiza RAM → `snapshot` por WebSocket → painel.
- **Comando:** botão → `POST /api/comandos/...` (202 + `commandId`) → mensagem XMPP com `id = commandId` → ESP32 responde
  (`device.status` ou `command.ack` com o mesmo `commandId`) → painel recebe `command.result`.
  Falhas: ESP32 offline ⇒ a mensagem volta ao backend ⇒ `FAILED`; sem resposta em 5 s ⇒ `TIMEOUT`.
- **ESP32 online/offline:** presença XMPP do resource `esp32` (imediato) + watchdog de 30 s sem mensagens (heartbeat do ESP32 = 10 s).
- **Reconstrução:** ao conectar, o backend envia `status.request`; o ESP32 também manda `device.status` ao conectar.

## Protocolo JSON (corpo da mensagem XMPP)
| type | sentido | campos |
|---|---|---|
| `parking.update` | ESP→BE | device, spot 1-4, status FREE/OCCUPIED, distanceCm? |
| `sensor.error` | ESP→BE | device, spot, status=FAULT |
| `device.online` | ESP→BE | device |
| `device.status` | ESP→BE | device, commandId?, spots[{spot,status,distanceCm?}] (heartbeat a cada 10 s) |
| `status.request` / `sensor.read` / `led.test` | BE→ESP | commandId |
| `command.ack` | ESP→BE | device, commandId, command, ok, detail? |

Backend só aceita mensagens do JID `conta/esp32`; ESP32 só aceita comandos de `conta/backend`.

## Firmware
Cliente XMPP mínimo próprio (`xmpp_client.cpp`, sobre `WiFiClient`): TCP, SASL PLAIN, bind, `<message>`, resposta a `iq get`,
keepalive, reconexão com backoff 1→30 s. **Sem TLS** (por isso as 2 linhas no Prosody; só LAN).
Sensores: leitura a cada 250 ms; 3 leituras iguais confirmam FREE/OCCUPIED (≤ 25 cm = ocupada); 5 inválidas = FAULT.
LEDs: verde livre, vermelho ocupada, ambos piscando = falha.

## Backend
Tudo no mesmo event loop (FastAPI + Slixmpp + sonda TCP do Prosody + watchdog). Rodar com **1 worker**.
