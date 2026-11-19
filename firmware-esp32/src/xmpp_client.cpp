#include "xmpp_client.h"
#include "mbedtls/base64.h"

static String xmlEscape(const String& s) {
  String o;
  o.reserve(s.length() + 16);
  for (size_t i = 0; i < s.length(); i++) {
    char c = s[i];
    if (c == '&') o += "&amp;";
    else if (c == '<') o += "&lt;";
    else if (c == '>') o += "&gt;";
    else o += c;
  }
  return o;
}

static String xmlUnescape(String s) {
  s.replace("&lt;", "<");
  s.replace("&gt;", ">");
  s.replace("&quot;", "\"");
  s.replace("&apos;", "'");
  s.replace("&amp;", "&");   // por último
  return s;
}

static String getAttr(const String& stanza, const char* name) {
  int gt = stanza.indexOf('>');
  String head = stanza.substring(0, gt < 0 ? stanza.length() : gt);
  String key = String(" ") + name + "=";
  int i = head.indexOf(key);
  if (i < 0) return "";
  i += key.length();
  char q = head[i];
  int e = head.indexOf(q, i + 1);
  if (e < 0) return "";
  return xmlUnescape(head.substring(i + 1, e));
}

static String saslPlain(const char* user, const char* pass) {
  uint8_t in[160];
  size_t u = strlen(user), p = strlen(pass), n = 0;
  if (u + p + 2 > sizeof(in)) return "";
  in[n++] = 0;
  memcpy(in + n, user, u); n += u;
  in[n++] = 0;
  memcpy(in + n, pass, p); n += p;
  uint8_t out[256];
  size_t olen = 0;
  mbedtls_base64_encode(out, sizeof(out), &olen, in, n);
  String s;
  s.concat((const char*)out, olen);
  return s;
}

void XmppClient::begin(const char* host, uint16_t port, const char* domain,
                       const char* user, const char* pass, const char* resource) {
  host_ = host; port_ = port; domain_ = domain;
  user_ = user; pass_ = pass; resource_ = resource;
}

void XmppClient::pump() {
  uint8_t tmp[256];
  while (client_.available()) {
    int n = client_.read(tmp, sizeof(tmp));
    if (n <= 0) break;
    buf_.concat((const char*)tmp, n);
    if (buf_.length() > 6000) buf_ = "";   // proteção de memória
  }
}

bool XmppClient::waitFor(const char* token, uint32_t timeoutMs) {
  uint32_t t0 = millis();
  while (millis() - t0 < timeoutMs) {
    pump();
    if (buf_.indexOf(token) >= 0) return true;
    if (!client_.connected()) return false;
    delay(5);
  }
  return false;
}

int XmppClient::waitForEither(const char* a, const char* b, uint32_t timeoutMs) {
  uint32_t t0 = millis();
  while (millis() - t0 < timeoutMs) {
    pump();
    if (buf_.indexOf(a) >= 0) return 1;
    if (buf_.indexOf(b) >= 0) return 2;
    if (!client_.connected()) return 0;
    delay(5);
  }
  return 0;
}

bool XmppClient::connectSession() {
  client_.stop();
  buf_ = "";
  Serial.printf("[xmpp] conectando %s:%u\n", host_, port_);
  if (!client_.connect(host_, port_, 5000)) return false;
  client_.setNoDelay(true);

  String open = String("<?xml version='1.0'?><stream:stream to='") + domain_ +
                "' xmlns='jabber:client' xmlns:stream='http://etherx.jabber.org/streams' version='1.0'>";

  client_.print(open);
  if (!waitFor("</stream:features>", 8000)) return false;
  if (buf_.indexOf("PLAIN") < 0) { Serial.println("[xmpp] servidor não oferece PLAIN"); return false; }

  String cred = saslPlain(user_, pass_);
  if (cred.isEmpty()) return false;
  client_.print(String("<auth xmlns='urn:ietf:params:xml:ns:xmpp-sasl' mechanism='PLAIN'>") + cred + "</auth>");
  buf_ = "";
  int r = waitForEither("<success", "<failure", 8000);
  if (r != 1) { Serial.println("[xmpp] autenticação falhou"); return false; }

  buf_ = "";
  client_.print(open);                                  // reinicia o stream após SASL
  if (!waitFor("</stream:features>", 8000)) return false;

  buf_ = "";
  client_.print(String("<iq type='set' id='bind1'><bind xmlns='urn:ietf:params:xml:ns:xmpp-bind'><resource>") +
                resource_ + "</resource></bind></iq>");
  if (!waitFor("</iq>", 8000) || buf_.indexOf("result") < 0) { Serial.println("[xmpp] bind falhou"); return false; }

  buf_ = "";
  client_.print("<presence/>");
  lastKeepalive_ = millis();
  Serial.println("[xmpp] sessão estabelecida");
  return true;
}

void XmppClient::drop() {
  if (online_) Serial.println("[xmpp] sessão encerrada");
  client_.stop();
  online_ = false;
  buf_ = "";
  nextAttempt_ = millis() + 1000;
  backoff_ = 1000;
}

bool XmppClient::justConnected() {
  bool j = justConnected_;
  justConnected_ = false;
  return j;
}

void XmppClient::loop() {
  if (WiFi.status() != WL_CONNECTED) {
    if (online_) drop();
    return;
  }
  if (!online_) {
    if ((int32_t)(millis() - nextAttempt_) < 0) return;
    if (connectSession()) {
      online_ = true;
      justConnected_ = true;
      backoff_ = 1000;
    } else {
      client_.stop();
      backoff_ = min<uint32_t>(backoff_ * 2, 30000);
      nextAttempt_ = millis() + backoff_;
      Serial.printf("[xmpp] nova tentativa em %u ms\n", backoff_);
    }
    return;
  }
  if (!client_.connected()) { drop(); return; }
  pump();
  processBuffer();
  if (online_ && millis() - lastKeepalive_ > 30000) {
    client_.print(" ");                                  // whitespace keepalive
    lastKeepalive_ = millis();
  }
}

void XmppClient::processBuffer() {
  while (online_) {
    int lt = buf_.indexOf('<');
    if (lt < 0) { buf_ = ""; return; }
    if (lt > 0) buf_.remove(0, lt);
    int gt = buf_.indexOf('>');
    if (gt < 0) return;

    int e = 1;
    while (e < (int)buf_.length() && !isspace(buf_[e]) && buf_[e] != '>' && buf_[e] != '/') e++;
    String name = buf_.substring(1, e);
    if (buf_[1] == '/') name = buf_.substring(1, gt);       // tag de fechamento, ex.: "/stream:stream"

    if (name.startsWith("?") || name == "stream:stream") { buf_.remove(0, gt + 1); continue; }
    if (name.startsWith("/")) {
      if (name == "/stream:stream") { drop(); return; }
      buf_.remove(0, gt + 1);
      continue;
    }

    String stanza;
    if (buf_[gt - 1] == '/') {
      stanza = buf_.substring(0, gt + 1);
      buf_.remove(0, gt + 1);
    } else {
      String close = "</" + name + ">";
      int c = buf_.indexOf(close);
      if (c < 0) return;                                  // stanza incompleta
      int end = c + close.length();
      stanza = buf_.substring(0, end);
      buf_.remove(0, end);
    }
    handleStanza(name, stanza);
  }
}

void XmppClient::handleStanza(const String& name, const String& stanza) {
  if (name == "message") {
    if (getAttr(stanza, "type") == "error") return;
    int b = stanza.indexOf("<body>");
    int e = stanza.indexOf("</body>");
    if (b < 0 || e < 0) return;
    String body = xmlUnescape(stanza.substring(b + 6, e));
    if (cb_) cb_(getAttr(stanza, "from"), body);
  } else if (name == "iq") {
    if (getAttr(stanza, "type") == "get") {               // ping do servidor, etc.
      client_.print("<iq type='result' id='" + getAttr(stanza, "id") + "' to='" + getAttr(stanza, "from") + "'/>");
    }
  }
}

bool XmppClient::sendMessage(const String& to, const String& body) {
  if (!online_) return false;
  String x = "<message type='chat' to='" + to + "'><body>" + xmlEscape(body) + "</body></message>";
  size_t w = client_.print(x);
  if (w != x.length()) { drop(); return false; }
  return true;
}
