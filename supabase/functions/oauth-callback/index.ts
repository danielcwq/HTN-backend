// deno-lint-ignore-file
import { serve } from "https://deno.land/std/http/server.ts";

const CLIENT_ID = Deno.env.get("GOOGLE_CLIENT_ID")!;
const CLIENT_SECRET = Deno.env.get("GOOGLE_CLIENT_SECRET")!;
const REDIRECT = Deno.env.get("SUPABASE_URL")! + "/functions/v1/oauth-callback";

async function exchangeCodeForTokens(code: string) {
  const res = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      code,
      client_id: CLIENT_ID,
      client_secret: CLIENT_SECRET,
      redirect_uri: REDIRECT,
      grant_type: "authorization_code",
    }),
  });
  if (!res.ok) throw new Error(await res.text());
  return await res.json();
}

serve(async (req) => {
  const url = new URL(req.url);
  const code = url.searchParams.get("code");
  const error = url.searchParams.get("error");
  if (error) return new Response(`OAuth error: ${error}`, { status: 400 });
  if (!code) return new Response("Missing code", { status: 400 });

  try {
    const tokens = await exchangeCodeForTokens(code);
    const { refresh_token, access_token, expires_in, scope } = tokens;

    if (!refresh_token) {
      return new Response(
        "No refresh_token returned. Re-run with prompt=consent & access_type=offline.",
        { status: 400 },
      );
    }

    // Show refresh token ONCE so you can copy it into Supabase secrets.
    const html = `
      <html><body style="font-family:system-ui;padding:24px">
        <h2>Copy your Google REFRESH TOKEN now</h2>
        <p><strong>Refresh Token:</strong></p>
        <pre style="white-space:pre-wrap;border:1px solid #ccc;padding:12px">${refresh_token}</pre>
        <p>Scopes: ${scope}</p>
        <p>Access token expires in: ${expires_in}s</p>
        <p style="color:#b00">After copying, delete or disable this function.</p>
      </body></html>`;
    return new Response(html, { headers: { "content-type": "text/html" } });
  } catch (e) {
    return new Response(`Token exchange failed: ${e}`, { status: 500 });
  }
});
