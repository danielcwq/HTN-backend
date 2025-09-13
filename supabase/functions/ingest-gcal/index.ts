// deno-lint-ignore-file no-explicit-any
import { serve } from "https://deno.land/std/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { refreshAccessToken } from "../_shared/google_oauth.ts";

const SB_URL = Deno.env.get("SUPABASE_URL")!;
const SB_KEY = Deno.env.get("SERVICE_ROLE_KEY")!;
const sb = createClient(SB_URL, SB_KEY);

const CLIENT_ID = Deno.env.get("GOOGLE_CLIENT_ID")!;
const CLIENT_SECRET = Deno.env.get("GOOGLE_CLIENT_SECRET")!;
const REFRESH = Deno.env.get("GOOGLE_REFRESH_TOKEN")!;

function toISO(d: string | undefined, tz = "America/Toronto"): string | null {
  // Calendar all-day events come as date (no time). Interpret in local TZ.
  if (!d) return null;
  // If it's a date 'YYYY-MM-DD', treat as local midnight → ISO
  if (/^\d{4}-\d{2}-\d{2}$/.test(d)) {
    // Construct as local midnight then convert to ISO
    const dt = new Date(`${d}T00:00:00`);
    return new Date(dt.getTime()).toISOString();
  }
  return new Date(d).toISOString();
}

serve(async () => {
  const accessToken = await refreshAccessToken(REFRESH, CLIENT_ID, CLIENT_SECRET);

  // Get the gcal source row
  const { data: src } = await sb.from("sources")
    .select("source_id, last_token")
    .eq("kind","gcal")
    .limit(1).single();
  if (!src) throw new Error("No sources row for kind='gcal'");

  let pageToken: string | undefined;
  let syncToken: string | undefined = src.last_token ?? undefined;

  // Build initial URL
  const base = new URL("https://www.googleapis.com/calendar/v3/calendars/primary/events");
  base.searchParams.set("singleEvents","true");
  base.searchParams.set("showDeleted","false");
  base.searchParams.set("maxResults","2500");
  // Use syncToken if we have one; otherwise do an initial 90-day backfill
  if (syncToken) {
    base.searchParams.set("syncToken", syncToken);
  } else {
    const timeMin = new Date(Date.now() - 90*86400_000).toISOString();
    base.searchParams.set("timeMin", timeMin);
  }

  do {
    const url = new URL(base.toString());
    if (pageToken) url.searchParams.set("pageToken", pageToken);

    const res = await fetch(url, { headers: { Authorization: `Bearer ${accessToken}` }});
    const json = await res.json();
    if (!res.ok) {
      // If syncToken is expired, clear it and let next run do a fresh load
      if (json?.error?.code === 410) {
        await sb.from("sources").update({ last_token: null }).eq("source_id", src.source_id);
        return new Response("syncToken expired; cleared", { status: 200 });
      }
      throw new Error(`gcal list failed: ${res.status} ${JSON.stringify(json)}`);
    }

    for (const ev of json.items ?? []) {
      // Compute ts_range
      const startISO = toISO(ev.start?.dateTime ?? ev.start?.date);
      const endISO   = toISO(ev.end?.dateTime ?? ev.end?.date);
      if (!startISO || !endISO) continue; // skip malformed

      const tsRange = `[${startISO},${endISO})`;

      const details = {
        summary: ev.summary ?? null,
        status: ev.status ?? null,
        location: ev.location ?? null,
        hangoutLink: ev.hangoutLink ?? null,
        attendees: (ev.attendees ?? []).map((a: any) => ({ email: a.email, responseStatus: a.responseStatus })),
        organizer: ev.organizer?.email ?? null
      };

      const { error } = await sb.from("events").upsert({
        kind: "calendar",
        ts_range: tsRange,
        ingested_at: new Date().toISOString(),
        source_id: src.source_id,
        source_ref: ev.id,
        confidence: 1.0,
        details
      }, { onConflict: "source_id,source_ref" });

      if (error) console.error("events upsert error", error);
    }

    pageToken = json.nextPageToken;
    syncToken = json.nextSyncToken ?? syncToken;
  } while (pageToken);

  // Persist latest syncToken + watermark
  await sb.from("sources").update({
    last_token: syncToken ?? null,
    watermark_ts: new Date().toISOString(),
    updated_at: new Date().toISOString()
  }).eq("source_id", src.source_id);

  return new Response("ok");
});
