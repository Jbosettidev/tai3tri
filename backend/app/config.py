"""Configuração por variáveis de ambiente (ver .env.example)."""
import os

NUM_SPOTS = 4
BACKEND_RESOURCE = "backend"   # resource do backend  -> parking@localhost/backend
DEVICE_RESOURCE = "esp32"      # resource do ESP32    -> parking@localhost/esp32


class Settings:
    def __init__(self) -> None:
        e = os.environ.get
        self.bare_jid = e("XMPP_JID", "parking@localhost")          # conta única
        self.password = e("XMPP_PASSWORD", "parking-pass")
        self.host = e("XMPP_HOST", "127.0.0.1")                      # onde o Prosody escuta
        self.port = int(e("XMPP_PORT", "5222"))
        self.backend_jid = f"{self.bare_jid}/{BACKEND_RESOURCE}"
        self.device_jid = f"{self.bare_jid}/{DEVICE_RESOURCE}"
        self.device_id = e("DEVICE_ID", "esp32-01")
        self.offline_after_s = float(e("OFFLINE_AFTER_S", "30"))
        self.command_timeout_s = float(e("COMMAND_TIMEOUT_S", "5"))


settings = Settings()
