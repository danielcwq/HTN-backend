// deno-lint-ignore-file no-explicit-any
import { serve } from "https://deno.land/std/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { refreshAccessToken } from "../_shared/google_oauth.ts";

const SB_URL = Deno.env.get("SUPABASE_URL")!;
const SB_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const sb = createClient(SB_URL, SB_KEY);

const CLIENT_ID = Deno.env.get("GOOGLE_CLIENT_ID")!;
const CLIENT_SECRET = Deno.env.get("GOOGLE_CLIENT_SECRET")!;
const REFRESH = Deno.env.get("GMAIL_REFRESH_TOKEN")!;
const WINDOW_DAYS = Number(Deno.env.get("GMAIL_QUERY_WINDOW_DAYS") ?? "14");

// Map RFC 2822 headers from Gmail metadata
function header(h: any[], name: string) {
  const f = h?.find((x: any) => x.name?.toLowerCase() === name.toLowerCase());
  return f?.value ?? null;
}

serve(async () => {
  const accessToken = await refreshAccessToken(REFRESH, CLIENT_ID, CLIENT_SECRET);

  // Grab source_id for Gmail
  const { data: src } = await sb.from("sources").select("source_id").eq("kind","gmail").limit(1).single();
  if (!src) throw new Error("No sources row for kind='gmail'");

  // Simple, robust strategy: scan last N days and upsert by message.id (dedupe via unique index)
  const afterISO = new Date(Date.now() - WINDOW_DAYS*86400_000);
  const q = `newer_than:${WINDOW_DAYS}d -category:{promotions social} -in:drafts`; // tune as you like

  // 1) List message ids
  let pageToken: string | undefined = undefined;
  const ids: string[] = [];
  do {
    const url = new URL(`https://gmail.googleapis.com/gmail/v1/users/me/messages`);
    url.searchParams.set("q", q);
    if (pageToken) url.searchParams.set("pageToken", pageToken);
    const res = await fetch(url, { headers: { Authorization: `Bearer ${accessToken}` }});
    const json = await res.json();
    (json.messages ?? []).forEach((m: any) => ids.push(m.id));
    pageToken = json.nextPageToken;
  } while (pageToken);

  // 2) Fetch metadata per id and upsert as events
  for (const id of ids) {
    const url = new URL(`https://gmail.googleapis.com/gmail/v1/users/me/messages/${id}`);
    url.searchParams.set("format","metadata");
    url.searchParams.append("metadataHeaders","From");
    url.searchParams.append("metadataHeaders","To");
    url.searchParams.append("metadataHeaders","Subject");
    url.searchParams.append("metadataHeaders","Date");
    url.searchParams.append("metadataHeaders","Message-Id");
    const res = await fetch(url, { headers: { Authorization: `Bearer ${accessToken}` }});
    if (!res.ok) {
      console.warn("gmail get failed", id, await res.text());
      continue;
    }
    const msg = await res.json();

    const dateMs = Number(msg.internalDate); // ms since epoch
    const sentAt = new Date(dateMs).toISOString();
    const tsRange = `[${sentAt},${sentAt})`;

    const hdrs = msg.payload?.headers ?? [];
    const details = {
      threadId: msg.threadId,
      from: header(hdrs,"From"),
      to: header(hdrs,"To"),
      subject: header(hdrs,"Subject"),
      messageId: header(hdrs,"Message-Id"),
      labelIds: msg.labelIds ?? [],
      // snippet is OK; avoid bodies for privacy
      snippet: msg.snippet ?? null,
    };

    const { error } = await sb.from("events").upsert({
      kind: "email",
      ts_range: tsRange,
      ingested_at: new Date().toISOString(),
      source_id: src.source_id,
      source_ref: msg.id,
      confidence: 1.0,
      details
    }, { onConflict: "source_id,source_ref" });

    if (error) console.error("events upsert error", error);
  }

  // Update watermark (last run time)
  await sb.from("sources")
    .update({ watermark_ts: new Date().toISOString(), updated_at: new Date().toISOString() })
    .eq("source_id", src.source_id);

  return new Response("ok");
});
