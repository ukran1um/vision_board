# TODO

## Soon

- [ ] **Lock down `/api/analyze` from public abuse** — the Codespaces public URL exposes both the HTML page and the raw Claude endpoint on the same port. Anyone with the URL can POST directly to `/api/analyze` and burn Anthropic credits. Need to pick one of the approaches below and implement. | Source: discussed during demo handoff

  Options, roughly ordered by effort:

  1. **Server-side Origin/Referer check (lowest effort, weakest)** — reject `/api/analyze` requests whose `Origin`/`Referer` header isn't the app's own URL. Trivially spoofable but filters casual abuse.
  2. **Signed short-lived session token (recommended)** — `GET /` returns the HTML with a server-HMAC-signed token embedded in a meta tag. Frontend sends it with every `POST /api/analyze`. Tokens expire after ~30 min. An attacker has to scrape the HTML first and can't just hit the API cold.
  3. **Rate limit by IP + daily cap** — slowapi/limits middleware. Doesn't prevent abuse but caps blast radius. Stack with option 2.
  4. **Cloudflare Turnstile or hCaptcha on first load** — real bot protection. Correct answer if this ever leaves demo territory.
  5. **Codespaces "Org" port visibility** — replaces "public" with GitHub-org-scoped auth. Only works if the demo audience is in an org you control.

  Recommendation: ship (2) + (3) together for the demo-stage default. Revisit (4) if this goes beyond internal demos.

## Someday

- [ ] **Export / save the curated reflections** — after a student agrees/disagrees/edits, give them a way to walk away with the result (PDF, shareable image, or plaintext). Currently the curated list only lives in the browser tab.
