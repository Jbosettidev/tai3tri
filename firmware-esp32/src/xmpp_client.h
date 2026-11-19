#pragma once
#include <Arduino.h>
#include <WiFi.h>

// Cliente XMPP mínimo p/ ESP32: TCP puro, SASL PLAIN, bind de resource,
// <message> com <body> (JSON). SEM TLS (somente LAN; ver ARQUITETURA.md).
typedef void (*XmppMessageCb)(const String& from, const String& body);

class XmppClient {
 public:
  void begin(const char* host, uint16_t port, const char* domain,
             const char* user, const char* pass, const char* resource);
  void onMessage(XmppMessageCb cb) { cb_ = cb; }
  void loop();                                   // chamar com frequência
  bool connected() const { return online_; }
  bool sendMessage(const String& to, const String& body);
  bool justConnected();                          // true uma vez após cada sessão nova

 private:
  bool connectSession();
  bool waitFor(const char* token, uint32_t timeoutMs);
  int  waitForEither(const char* a, const char* b, uint32_t timeoutMs);
  void pump();
  void processBuffer();
  void handleStanza(const String& name, const String& stanza);
  void drop();

  WiFiClient client_;
  String buf_;
  const char *host_, *domain_, *user_, *pass_, *resource_;
  uint16_t port_ = 5222;
  XmppMessageCb cb_ = nullptr;
  bool online_ = false, justConnected_ = false;
  uint32_t nextAttempt_ = 0, backoff_ = 1000, lastKeepalive_ = 0;
};
