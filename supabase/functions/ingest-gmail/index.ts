// supabase/functions/ingest-gmail/index.ts
import { serve } from "https://deno.land/std/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

console.log("CLIENT_ID:", (Deno.env.get("GOOGLE_CLIENT_ID")||"").slice(0,12), "…");
console.log("Using refresh token:", (Deno.env.get("GOOGLE_REFRESH_TOKEN")||"").slice(0,8), "…");


async function refreshAccessToken(refreshToken: string, clientId: string, clientSecret: string) {
  const res = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      client_id: clientId,
      client_secret: clientSecret,
      refresh_token: refreshToken,
      grant_type: "refresh_token",
    }),
  });
  const text = await res.text();
  if (!res.ok) throw new Error(`Token refresh failed: ${res.status} ${text}`);
  const json = JSON.parse(text);
  return json.access_token as string;
}

serve(async () => {
  const debug: Record<string, unknown> = {};
  try {
    // 0) Env check
    const SB_URL = Deno.env.get("SUPABASE_URL");
    const SB_KEY = Deno.env.get("SERVICE_ROLE_KEY");
    const CLIENT_ID = Deno.env.get("GOOGLE_CLIENT_ID");
    const CLIENT_SECRET = Deno.env.get("GOOGLE_CLIENT_SECRET");
    const REFRESH = Deno.env.get("GOOGLE_REFRESH_TOKEN");

    const missing = Object.entries({ SB_URL, SB_KEY, CLIENT_ID, CLIENT_SECRET, REFRESH })
      .filter(([, v]) => !v).map(([k]) => k);
    if (missing.length) {
      debug.missing_envs = missing;
      return new Response(JSON.stringify({ ok: false, debug }), { status: 500, headers: { "content-type": "application/json" } });
    }

    const sb = createClient(SB_URL!, SB_KEY!, { auth: { persistSession: false } });

    // 1) Access token
    const accessToken = await refreshAccessToken(REFRESH!, CLIENT_ID!, CLIENT_SECRET!);
    debug.token = "ok";

    // 2) Source row
    const { data: src, error: srcErr } = await sb.from("sources").select("source_id").eq("kind","gmail").limit(1).single();
    if (srcErr || !src) {
      debug.source_error = srcErr ?? "no gmail source row";
      return new Response(JSON.stringify({ ok: false, debug }), { status: 500, headers: { "content-type": "application/json" } });
    }
    debug.source_id = src.source_id;

    // 3) List a small batch of message IDs (7 days)
    const listUrl = new URL("https://gmail.googleapis.com/gmail/v1/users/me/messages");
    listUrl.searchParams.set("q", "newer_than:7d -in:drafts");
    listUrl.searchParams.set("maxResults","10");
    const listRes = await fetch(listUrl, { headers: { Authorization: `Bearer ${accessToken}` } });
    const listText = await listRes.text();
    if (!listRes.ok) {
      debug.gmail_list_error = { status: listRes.status, body: listText.slice(0, 400) };
      return new Response(JSON.stringify({ ok:false, debug }), { status: 500, headers: { "content-type": "application/json" } });
    }
    const listJson = JSON.parse(listText);
    const ids: string[] = (listJson.messages ?? []).map((m: any) => m.id);
    debug.listed_ids = ids.length;

    // 4) Fetch metadata for each ID and upsert a few
    let inserted = 0;
    for (const id of ids) {
      const url = new URL(`https://gmail.googleapis.com/gmail/v1/users/me/messages/${id}`);
      url.searchParams.set("format","metadata");
      url.searchParams.append("metadataHeaders","From");
      url.searchParams.append("metadataHeaders","To");
      url.searchParams.append("metadataHeaders","Subject");
      url.searchParams.append("metadataHeaders","Date");
      const res = await fetch(url, { headers: { Authorization: `Bearer ${accessToken}` } });
      const txt = await res.text();
      if (!res.ok) {
        debug.gmail_get_error = { status: res.status, body: txt.slice(0, 400) };
        return new Response(JSON.stringify({ ok:false, debug }), { status: 500, headers: { "content-type": "application/json" } });
      }
      const msg = JSON.parse(txt);
      if (!debug.sample) {
        const hdrs = msg.payload?.headers ?? [];
        debug.sample = {
          id: msg.id,
          internalDate: msg.internalDate,
          snippet: msg.snippet,
          headers: {
            From: hdrs.find((h: any) => h.name === "From")?.value ?? null,
            Subject: hdrs.find((h: any) => h.name === "Subject")?.value ?? null,
            Date: hdrs.find((h: any) => h.name === "Date")?.value ?? null,
          }
        };
      }
      const hdrs = msg.payload?.headers ?? [];
      const get = (name: string) =>
        hdrs.find((h: any) => h.name?.toLowerCase() === name.toLowerCase())?.value ?? null;

      // Prefer Gmail's internalDate (epoch ms). Fallback to RFC2822 Date header.
      const ms = Number(msg.internalDate ?? 0) || Date.parse(get("Date") ?? "");
      if (!ms || Number.isNaN(ms)) {
        console.error("Missing/invalid timestamp for message", msg.id);
        continue; // Skip this message
      }

      // Build a **non-empty** 1-second range for point events
      const startISO = new Date(ms).toISOString();
      const endISO   = new Date(ms + 1000).toISOString(); // +1s
      const tsRange  = `[${startISO},${endISO})`;

      const { error } = await sb.from("events").upsert({
        kind: "email",
        ts_range: tsRange,                 // <-- IMPORTANT
        source_id: src.source_id,
        source_ref: msg.id,
        confidence: 1.0,
        details: {
          threadId: msg.threadId,
          from: get("From"),
          to: get("To"),
          subject: get("Subject"),
          date_header: get("Date"),        // keep the raw Date header too (optional)
          internalDate: ms,                // <-- store epoch ms for future backfills
          labelIds: msg.labelIds ?? [],
          snippet: msg.snippet ?? null
        }
      }, { onConflict: "source_id,source_ref" });
      if (error) {
        debug.upsert_error = {
          code: error.code,
          message: error.message,
          details: error.details,
          hint: error.hint,
        };
        return new Response(JSON.stringify({ ok:false, debug }), {
          status: 500, headers: { "content-type": "application/json" }
        });
      }
      inserted++;
    }

    debug.inserted = inserted;
    return new Response(JSON.stringify({ ok: true, debug }), { status: 200, headers: { "content-type": "application/json" } });
  } catch (e) {
    debug.error = e instanceof Error ? e.message : JSON.stringify(e);
    return new Response(JSON.stringify({ ok: false, debug }), { status: 500, headers: { "content-type": "application/json" } });
  }
});
