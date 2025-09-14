// supabase/functions/ingest-gcal/index.ts
import { serve } from "https://deno.land/std/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { refreshAccessToken } from "../_shared/google_oauth.ts";

const sb = createClient(
  Deno.env.get("SUPABASE_URL")!,
  Deno.env.get("SERVICE_ROLE_KEY")!
);

const CLIENT_ID = Deno.env.get("GOOGLE_CLIENT_ID")!;
const CLIENT_SECRET = Deno.env.get("GOOGLE_CLIENT_SECRET")!;
const REFRESH = Deno.env.get("GOOGLE_REFRESH_TOKEN")!;

function toIso(d: string): string {
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

  // Build initial URL with VERY LIMITED time range
  const base = new URL("https://www.googleapis.com/calendar/v3/calendars/primary/events");
  base.searchParams.set("singleEvents","true");
  base.searchParams.set("showDeleted","false");
  base.searchParams.set("maxResults","50"); // VERY LIMITED: Only 50 events max
  
  // Use syncToken if we have one; otherwise do a VERY LIMITED backfill
  if (syncToken) {
    base.searchParams.set("syncToken", syncToken);
  } else {
    // VERY LIMITED: Only get events from last 3 days to next 14 days
    const timeMin = new Date(Date.now() - 3*86400_000).toISOString();  // 3 days back
    const timeMax = new Date(Date.now() + 14*86400_000).toISOString(); // 14 days forward
    base.searchParams.set("timeMin", timeMin);
    base.searchParams.set("timeMax", timeMax);
    console.log(`Very limited ingestion: ${timeMin} to ${timeMax} (max 50 events)`);
  }

  let eventCount = 0;
  do {
    const url = new URL(base.toString());
    if (pageToken) url.searchParams.set("pageToken", pageToken);

    const res = await fetch(url, { headers: { Authorization: `Bearer ${accessToken}` }});
    const json = await res.json();
    if (!res.ok) {
      // If syncToken is expired, clear it and let next run do a fresh load
      if (res.status === 410) {
        await sb.from("sources").update({last_token: null}).eq("source_id", src.source_id);
      }
      console.error("gcal list failed:", res.status, json);
      return new Response(`gcal failed: ${res.status}`, { status: 500 });
    }

    // Process events
    for (const item of json.items ?? []) {
      if (item.status === "cancelled") {
        await sb.from("events").delete()
          .eq("source_id", src.source_id)
          .eq("source_ref", item.id);
        continue;
      }

      const start = item.start?.dateTime || item.start?.date;
      const end = item.end?.dateTime || item.end?.date;
      if (!start || !end) continue;

      let startIso: string, endIso: string;
      const allDay = !item.start?.dateTime;
      if (allDay) {
        startIso = toIso(start);
        endIso = toIso(end);
      } else {
        startIso = new Date(start).toISOString();
        endIso = new Date(end).toISOString();
      }

      await sb.from("events").upsert({
        kind: "calendar",
        ts_range: `[${startIso},${endIso})`,
        source_id: src.source_id,
        source_ref: item.id,
        confidence: 1.0,
        details: {
          summary: item.summary || null,
          status: item.status || null,
          location: item.location || null,
          description: item.description || null,
          attendees: item.attendees || null,
          created: item.created || null,
          updated: item.updated || null
        },
        ingested_at: new Date().toISOString()
      }, { onConflict: "source_id,source_ref" });

      eventCount++;
    }

    pageToken = json.nextPageToken;
    syncToken = json.nextSyncToken;

    // SAFETY: Stop if we've processed too many events
    if (eventCount >= 50) {
      console.log(`Reached event limit of 50, stopping ingestion`);
      break;
    }

  } while (pageToken);

  // Persist latest syncToken + watermark
  await sb.from("sources").update({
    last_token: syncToken ?? null,
    watermark_ts: new Date().toISOString(),
    updated_at: new Date().toISOString()
  }).eq("source_id", src.source_id);

  console.log(`Limited calendar ingestion complete. Events processed: ${eventCount}. SyncToken: ${syncToken ? 'updated' : 'none'}`);
  return new Response("ok");
});
