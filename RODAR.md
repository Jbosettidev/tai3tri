# Rodar (Fedora)

```bash
# 1. Prosody (uma vez)
sudo systemctl restart prosody
sudo prosodyctl register parking localhost parking-pass
sudo firewall-cmd --add-port=5222/tcp --add-port=8000/tcp --permanent && sudo firewall-cmd --reload

# 2. Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export XMPP_JID=parking@localhost XMPP_PASSWORD=parking-pass
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 3. Sem hardware (outro terminal, na pasta backend)
source .venv/bin/activate
export XMPP_JID=parking@localhost XMPP_PASSWORD=parking-pass
python -m tools.fake_esp32

# 4. Firmware
cd firmware-esp32
cp include/secrets.h.example include/secrets.h   # editar: Wi-Fi, XMPP_HOST=$(hostname -I)
pio run -t upload && pio device monitor
```

Painel: http://localhost:8000
