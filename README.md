# LaunchWise
The market-aware business builder for first-time entrepreneurs.

**Live:** https://launchwise.pro · Example starter page: https://launchwise.pro/s/example-pune-cakes

## What it is
You give LaunchWise a business idea and your real constraints: budget, how many items you can make a day, which days and how many hours you can work. It checks the idea with deterministic feasibility math, compares it with alternative options using a small sourced market dataset, and recommends one (or keeping your original idea). If you like the result, it can build a simple starter page for the idea, show you a preview, and, only after you click **Approve and publish**, put that page live at `/s/<name>` for 7 days.

The demo scenario used throughout: a home bakery in Pune, ₹10,000 budget, about 3 cakes a day, weekends only. In it, "everyday cakes" barely pay and "custom celebration cakes" score higher, so the app recommends the pivot. Three other guided scenarios show the original idea winning, nothing being viable, and a Noida business with no market data (feasibility only).

**Who the numbers come from:** Python, never Claude. Claude only reads text in and explains results out.

## How it works

```
Browser (React + Tailwind)
   │  HTTPS
Caddy ── automatic HTTPS, security headers, request-size caps, static frontend
   │  /api/*  and  /s/*
FastAPI backend  (routes → services → engine)
   ├─ engine/      pure feasibility + scoring + approval rules (no I/O)
   ├─ Claude       Intake (text → draft form) and Explain (numbers → plain words)
   ├─ approvals    hash-bound, single-use approvals, deploy guard, audit log
   └─ SQLite       live pages, expiry, token hashes, audit  (Docker volume /data)
```

- **Engine** (`backend/app/engine/`): feasibility numbers (startup cost, margin, weekly capacity, break-even, budget check), each tagged with where it came from (`user_provided`, `derived`, `estimate`, `assumption`, `from_source`). Money is `Decimal`, never a float. The engine imports nothing that does I/O, and a test enforces that.
- **Market data** (`backend/app/data/market_opportunities.json`): hand-curated Pune bakery entries with a source name, URL, retrieval date and verification status. The market signal feeds the ranking. Any other place or business still gets a feasibility-only analysis with a neutral market score and no pivots; nothing is invented.
- **Ranking** (`compare_strategies`): scores options on feasibility and market signal, explains each score, and lists plain-language caveats (assumed inputs, weak or contrary evidence, missing skills or equipment).
- **Claude, in two places only** (model name from the `CLAUDE_MODEL` env var, never in code):
  - **Explain:** writes a 3 to 5 sentence summary of a finished analysis. A post-check rejects the text if it uses a number that is not in the engine's results, names an unknown source, promises profit, misdescribes contrary evidence, or contains markup. It gets one retry, then a fixed template is used instead. The response says which one it was.
  - **Intake:** turns a free-text description of an idea (up to 1,500 characters) into a draft of the form fields. The visitor reviews and edits it; nothing runs until they submit the form.
  Claude outputs validated JSON or plain text only, never HTML or code. With no key set, or when call caps are spent (20 per visitor session, 500 overall, both configurable), the app falls back cleanly and still works.
- **Starter pages** (approval-guarded):
  1. **Preview:** the owner enters a business name, an optional description and email, and an offer (prefilled from the recommendation). The server renders the page from a business-agnostic `StorefrontConfig` template, with all text escaped, and requests an approval bound to the hash of that exact config. The preview shows in a fully sandboxed frame. Nothing is public.
  2. **Approve and publish:** the one explicit click grants the strategy and launch approvals server-side, each written to the audit log. The **deploy guard** then consumes the launch approval and refuses to run unless a matching one exists. The "deployer" stores the page.
  3. **Live:** every page carries `noindex` and an "Example page made with LaunchWise" banner and expires after 7 days. At most 50 are live and 3 can be published per visitor per hour. The owner gets a private unpublish link once, whose secret is kept after `#` so it is never sent to a server; only a hash of it is stored.
  4. Text rules: no HTML, links or images; the contact email is shown as plain text; a small whole-word blocklist is refused with fixed text.
  A seeded example page, `/s/example-pune-cakes`, is built at startup from the pivot scenario, never expires and cannot be unpublished through the public flow.
- **SQLite** on a Docker volume (`/data`): live pages, expiry, unpublish-token hashes, append-only page events and the approval audit log. Drafts and previews stay in memory. Audit records hold hashes, never page text, tokens or visitor addresses.
- **Contact form:** validation, honeypot, rate limits and header-injection protection, sent by SMTP. Off by default (`CONTACT_ENABLED=false`, answers 503, no SMTP).

## How GoDaddy is used
- **Hosting:** the app runs on a GoDaddy VPS (Ubuntu 24.04) with Docker Compose.
- **Domain:** `launchwise.pro`; `www.` redirects to it.
- **Mail:** the contact form sends through a GoDaddy mailbox over SMTP (`smtpout.secureserver.net`, port 465, SSL). The port and mode are still marked `TODO(verify)` against GoDaddy's own documentation.
- **No GoDaddy API is called.** Publishing a starter page stores it in the app's own database and serves it from our domain; it does not buy domains or touch GoDaddy services.

## Run it locally
Requires Python 3.11+ and Node.js.

```bash
cp .env.example .env     # placeholders only; .env is gitignored. Everything works without real values
make venv                # create .venv and install pinned backend deps
make run-backend         # http://localhost:8000/api/health
make run-frontend        # http://localhost:5173 (in a second terminal; run `npm install` in frontend/ once)
```

Without an Anthropic key the Explain and Intake features use their fallbacks. To try Claude, set `ANTHROPIC_API_KEY` and `CLAUDE_MODEL` in `.env`. Without mailbox values the contact form answers "not configured". Development serves interactive API docs at `http://localhost:8000/docs`; they are off in production.

### Try the analyze API
`POST /api/analyze` needs no login and makes no Claude calls. The four guided scenarios are JSON files in `backend/app/data/demo_scenarios/`:

```bash
curl -s http://localhost:8000/api/analyze -H 'Content-Type: application/json' \
  --data @backend/app/data/demo_scenarios/a_alternative_beats_thin_margin_original.json | python3 -m json.tool
```

Money in responses is always a string. Error replies name the field and a fixed message and never echo what you sent.

## Tests
| Command | What it runs |
|---|---|
| `make check` | backend: `ruff check`, `ruff format --check`, `mypy`, `pytest` (about 1,830 tests) |
| `make test` | backend `pytest` only |
| `make check-frontend` | frontend: eslint, type check, vitest (about 380 tests) |
| `make check-dataset` | fails while any market entry is a placeholder or unverified; run before submission |

Notable tests: the engine has no I/O imports; the deploy guard refuses without a matching approval and for a forged payload; sentinel strings never reach logs, audit records or error bodies; the Caddyfile and compose file are checked (size caps, headers, volume, non-root), and a test runs a real Caddy container when Docker is available. Claude, mail and the clock are injected, so tests use fakes and never touch the network.

## Deploy
Two containers, both non-root: **Caddy** (automatic HTTPS, `www` redirect, the built frontend, proxies `/api` and `/s/<slug>` to the backend) and the **backend**. Only ports 80 and 443 are public; the backend publishes nothing.

On the VPS, with Docker and Compose installed and DNS A records for `launchwise.pro` and `www.launchwise.pro` pointing at it:

```bash
git clone https://github.com/sharmamukti3011/LaunchWise.git && cd LaunchWise
cp .env.example .env && chmod 600 .env   # fill in real values; this file never leaves the server
docker compose up -d --build
curl -fsS https://launchwise.pro/api/health
```

- **Secrets** live only in the server-side `.env`, loaded through `env_file` into the backend. They are not in the repo, the images or the compose file.
- **Data:** the SQLite file lives on the `launchwise-data` volume and survives `docker compose up -d --build`. Certificates live in `caddy-data`. Do not run `docker compose down -v`: it deletes both, losing live pages and forcing new certificate requests that can hit Let's Encrypt limits.
- **Contact form:** to enable it, fill the `SMTP_*` and `CONTACT_RECIPIENT` values, set `CONTACT_ENABLED=true`, then `docker compose up -d --force-recreate backend`. If a value is missing or still an example, the app still starts and the form answers "not configured"; the startup log names the missing variables, never their values. The recipient is fixed in `.env`.
- **Limits are env-tunable** (see `.env.example`): contact (default 5 per visitor per hour, 200 per hour overall), analyze (60 per minute), publishing (`PUBLISH_LIMIT_PER_HOUR`, `MAX_LIVE_PAGES`), Claude call caps. Rate limits key on the real visitor address: Caddy sets `X-Forwarded-For` and the backend trusts it only from Caddy's fixed address.
- **Logs** hold outcomes only, never personal data: uvicorn runs with `--no-access-log` (do not remove it) and Caddy has no request log.
- **HSTS starts short** (`max-age=300`, no `includeSubDomains`, no `preload`) so a mistake is cheap to undo. Raise it in `frontend/Caddyfile` in steps once launch works.
- **Headers:** Caddy sets a Content-Security-Policy of `default-src 'self'; frame-ancestors 'none'` (no inline styles, which is why starter pages load their stylesheet from `/api/storefront/style.css`), plus `nosniff`, `X-Frame-Options: DENY`, a referrer policy and a permissions policy.
- **Network:** the compose network uses the fixed subnet `10.77.0.0/24`. `TODO(verify)`: it must not clash with another network on the VPS.
- **Non-root ports:** Caddy binds 80 and 443 as an unprivileged user via the `net.ipv4.ip_unprivileged_port_start=0` sysctl. It worked locally; `TODO(verify)` on the VPS. If the host refuses it, fall back to `cap_add: [NET_BIND_SERVICE]` with `setcap` in `frontend/Dockerfile`.
- **Local smoke test of the full stack:** set `SITE_DOMAIN=localhost` in `.env`, run `docker compose up -d --build`, then `curl -k https://localhost/api/health` (`-k` because Caddy issues a local certificate).
- Base images are not yet pinned by digest (`TODO(verify)`); do that on the server.

## Honest limits
- **Some figures are assumptions.** Weekly hours, time per item and the working-capital reserve may be assumed rather than given by the owner, and demand is modelled at 25%, 50% and 100% of capacity. Every such figure is tagged `assumption` or `estimate` and listed in the caveats; none is presented as a finding.
- **The market dataset is five Pune bakery entries.** It is small, hand-curated, and covers one city and one kind of business. Anything else gets feasibility-only analysis with a neutral market score. A recommendation is a comparison against this thin evidence, not a forecast or a promise of profit.
- **The "what the agent did" steps are a replay.** The analysis is deterministic and finishes in one request; the app then replays its recorded step log with a short animation. It is labelled "replay of recorded steps". It is not a live agent loop.
- **Guided scenarios are simulated.** Their inputs and prices are made up for the walkthrough and labelled so.
- **Starter pages are examples, not a real storefront.** They last 7 days, carry a banner, are hidden from search engines, take no orders or payments, and have no images or links. There are no user accounts: the unpublish link is the only control the owner has.
- **No rollback or staging.** Publishing stores the approved page directly. There is no previous-version rollback for pages.
- **Drafts live in memory,** so a restart loses unpublished previews (published pages are in SQLite and survive). The backend runs as a single worker.
- **Rate limits are per process** and keyed on the visitor's address.
- **The blocklist is deliberately small.** It is a guard rail, not moderation.

## Future scope
Not built; for the demo talk only.
- Hindi / English toggle.
- Trend-based seller offers.
- More cities and more business types in the market dataset.
- Rollback of a published page to a previous version.
- Domain-name suggestions through GoDaddy.

## Docs
`docs/SPEC.md` (behaviour of each part) and `docs/ENGINEERING.md` (engineering standards).
