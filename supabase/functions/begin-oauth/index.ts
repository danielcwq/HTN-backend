// deno-lint-ignore-file
import { serve } from "https://deno.land/std/http/server.ts";

const CLIENT_ID = Deno.env.get("GOOGLE_CLIENT_ID")!;
const REDIRECT = "https://idtxsrrhbjmdsbagzgqy.supabase.co/functions/v1/oauth-callback";
console.log("begin-oauth using CLIENT_ID =", CLIENT_ID, "REDIRECT =", REDIRECT);


// Request BOTH scopes at once so one refresh token covers Gmail + Calendar.
const SCOPES = [
  "https://www.googleapis.com/auth/gmail.readonly",
  "https://www.googleapis.com/auth/calendar.readonly",
].join(" ");

function urlEncode(obj: Record<string, string>) {
  const p = new URLSearchParams(obj);
  return p.toString();
}

serve((_req) => {
  const state = crypto.randomUUID(); // single-user; you can ignore verifying it
  const params = urlEncode({
    client_id: CLIENT_ID,
    redirect_uri: REDIRECT,
    response_type: "code",
    scope: SCOPES,
    access_type: "offline",   // IMPORTANT: get refresh_token
    prompt: "consent",        // force refresh_token even if previously granted
    include_granted_scopes: "true",
    state,
  });
  const authUrl = `https://accounts.google.com/o/oauth2/v2/auth?${params}`;
  return new Response(null, { status: 302, headers: { Location: authUrl } });
});
