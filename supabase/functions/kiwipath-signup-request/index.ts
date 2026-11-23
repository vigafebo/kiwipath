const allowedOrigin = Deno.env.get("SIGNUP_ORIGIN") || "https://vigafebo.github.io";

Deno.serve(async (request) => {
  const origin = request.headers.get("origin");
  const headers = {
    "Content-Type": "application/json",
    "Cache-Control": "no-store",
    "Vary": "Origin",
  };
  if (origin === allowedOrigin) headers["Access-Control-Allow-Origin"] = origin;
  const reply = (status, code) =>
    new Response(JSON.stringify({ code }), { status, headers });

  if (origin !== allowedOrigin) return reply(403, "forbidden");
  if (request.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: {
      ...headers,
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "content-type, apikey",
    }});
  }
  if (request.method !== "POST") return reply(405, "method");
  if (!request.headers.get("content-type")?.startsWith("application/json")) {
    return reply(415, "invalid");
  }

  const url = Deno.env.get("SIGNUP_SCRIPT_URL");
  const secret = Deno.env.get("SIGNUP_SCRIPT_SECRET");
  if (!url || !secret) return reply(503, "unavailable");
  if (!/^https:\/\/script\.google\.com\/macros\/s\/[\w-]+\/exec$/.test(url)) {
    return reply(503, "unavailable");
  }

  let body;
  try {
    if (Number(request.headers.get("content-length")) > 2048) return reply(413, "invalid");
    const raw = await request.text();
    if (raw.length > 2048) return reply(413, "invalid");
    body = JSON.parse(raw);
  } catch {
    return reply(400, "invalid");
  }
  const name = typeof body?.name === "string" ? body.name.trim() : "";
  const email = typeof body?.email === "string" ? body.email.trim() : "";
  const birth = body?.birth;
  const id = body?.id;
  const date = new Date(typeof birth === "string" ? birth + "T00:00:00Z" : NaN);
  if (!name || name.length > 120 || /[\r\n]/.test(name) ||
      email.length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) ||
      typeof birth !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(birth) ||
      !Number.isFinite(date.getTime()) || date.toISOString().slice(0, 10) !== birth ||
      birth > new Date().toISOString().slice(0, 10) ||
      typeof id !== "string" || !/^[a-f0-9-]{36}$/.test(id) || body.website) {
    return reply(400, "invalid");
  }
  try {
    const response = await fetch(url, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ secret, name, email, birth, id }),
      signal: AbortSignal.timeout(12000),
    });
    if (!response.ok) return reply(502, "retry");
    const result = await response.json();
    if (result.code === "sent") return reply(200, "sent");
    if (result.code === "limit") return reply(429, "limit");
    if (result.code === "unavailable") return reply(503, "unavailable");
    return reply(502, "retry");
  } catch {
    return reply(502, "retry");
  }
});
