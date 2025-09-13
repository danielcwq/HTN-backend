// supabase/functions/compute-features-snapshot/index.ts
// Writes a versioned snapshot of simple counts into features_window.
//
// Secrets needed (in your project):
//   SUPABASE_DB_URL = postgres://postgres:<password>@db.<host>:5432/postgres
//
// Optional body payload to override defaults:
//   { "sleep_minutes": 263, "sleep_score": 58, "spec_version": "v1" }

import { serve } from "https://deno.land/std@0.224.0/http/server.ts";
import postgres from "https://deno.land/x/postgresjs@v3.4.3/mod.js";

const DB_URL = Deno.env.get("DATABASE_URL");
if (!DB_URL) throw new Error("Missing SUPABASE_URL secret");

const sql = postgres(DB_URL, { prepare: false, max: 1, connect_timeout: 5, idle_timeout: 5 });

serve(async (req) => {
  if (req.method !== "POST") {
    return new Response("Use POST", { status: 405 });
  }

  const now = new Date(); // only for logging/response
  const body = await req.json().catch(() => ({}));

  const sleep_minutes = Number.isFinite(body.sleep_minutes) ? body.sleep_minutes : 263; // 4h23m
  const sleep_score   = Number.isFinite(body.sleep_score)   ? body.sleep_score   : 58;
  const spec_version  = typeof body.spec_version === "string" ? body.spec_version : "v1";

  try {
    // --- SQL counts (run on the DB clock to avoid drift) ---
    const [emailCountRow] = await sql/* sql */`
      SELECT COUNT(*)::int AS c
      FROM events
      WHERE kind = 'email'
        AND ts_range && tstzrange(now() - interval '12 hours', now(), '[)')`;

    const [eventCountRow] = await sql/* sql */`
      SELECT COUNT(*)::int AS c
      FROM events
      WHERE kind = 'calendar'
        AND ts_range && tstzrange(now() - interval '24 hours', now(), '[)')`;

    const emails_12h_count = emailCountRow.c as number;
    const events_24h_count = eventCountRow.c as number;

    // --- Upsert the feature window ---
    // We use window_size='12 hours' to denote the horizon of primary stats.
    // It's fine to include a 24h stat in the same JSON as long as it's named clearly.
    const [row] = await sql/* sql */`
      INSERT INTO features (window_end, window_size, spec_version, features)
      VALUES (
        now(),
        interval '12 hours',
        ${spec_version},
        ${sql.json({
          emails_12h_count,
          events_24h_count,
          sleep_minutes,
          sleep_score,
        })}
      )
      ON CONFLICT (window_end, window_size, spec_version)
      DO UPDATE SET
        features   = features.features || EXCLUDED.features,
        created_at = now()
      RETURNING window_end, window_size, spec_version, features, created_at
    `;

    return new Response(
      JSON.stringify(
        {
          ok: true,
          computed_at_utc: now.toISOString(),
          features_written: row,
        },
        null,
        2,
      ),
      { headers: { "content-type": "application/json" } },
    );
  } catch (err) {
    console.error(err);
    return new Response(JSON.stringify({ ok: false, error: String(err) }), {
      status: 500,
      headers: { "content-type": "application/json" },
    });
  }
});
