function doPost(event) {
  const reply = code => ContentService.createTextOutput(JSON.stringify({ code }))
    .setMimeType(ContentService.MimeType.JSON);
  const properties = PropertiesService.getScriptProperties();
  const secret = properties.getProperty("SIGNUP_SCRIPT_SECRET");
  const raw = event?.postData?.contents || "";
  if (!secret || secret.length < 32 || raw.length > 4096) return reply("unavailable");

  let body;
  try { body = JSON.parse(raw); } catch { return reply("invalid"); }
  if (typeof body?.secret !== "string" || body.secret.length !== secret.length) {
    return reply("unavailable");
  }
  let difference = 0;
  for (let i = 0; i < secret.length; i++) {
    difference |= secret.charCodeAt(i) ^ body.secret.charCodeAt(i);
  }
  if (difference) return reply("unavailable");

  const { name, email, birth, id } = body;
  if (typeof name !== "string" || !name.trim() || name.length > 120 || /[\r\n]/.test(name) ||
      typeof email !== "string" || email.length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) ||
      typeof birth !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(birth) ||
      typeof id !== "string" || !/^[a-f0-9-]{36}$/.test(id)) return reply("invalid");

  const lock = LockService.getScriptLock();
  if (!lock.tryLock(4000)) return reply("retry");
  try {
    const cache = CacheService.getScriptCache();
    if (cache.get(id)) return reply("sent");

    const now = Date.now();
    const recent = (JSON.parse(properties.getProperty("SIGNUP_SEND_TIMES") || "[]"))
      .filter(value => value > now - 86400000);
    if (recent.length >= 30 || recent.filter(value => value > now - 600000).length >= 6 ||
        MailApp.getRemainingDailyQuota() < 1) return reply("limit");

    MailApp.sendEmail({
      to: "info.kiwipath@gmail.com",
      replyTo: email,
      subject: "Solicitação de cadastro no KiwiPath",
      body: ["Nome: " + name, "E-mail: " + email, "Data de nascimento: " + birth].join("\n"),
    });
    cache.put(id, "sent", 21600);
    properties.setProperty("SIGNUP_SEND_TIMES", JSON.stringify([...recent, now]));
    return reply("sent");
  } catch {
    return reply("retry");
  } finally {
    lock.releaseLock();
  }
}
