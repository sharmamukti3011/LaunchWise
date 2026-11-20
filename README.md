# LaunchWise: The Feasibility-First Business Builder
Test a business idea against your real budget, time and skills before you spend anything.

Small businesses rarely have an easy way to check whether an idea is viable before they commit their savings. LaunchWise is an AI-assisted business builder, powered by Claude, that gives them that check in minutes, with verified market evidence where it has it and an honest feasibility-only check everywhere else.

**Live:** https://launchwise.pro · Example starter page: https://launchwise.pro/s/example-pune-cakes

## The problem
Many small business owners in India start with limited savings and limited time. A wrong first choice can use up the whole budget, and they have no easy way to check beforehand whether an idea's margin, startup cost and weekly hours actually work together.

## What LaunchWise does
1. **Describe your idea in plain words.** Claude turns it into a form, filling only what you said and flagging everything else for you to fill in. It never invents a number.
2. **Check feasibility first.** A deterministic engine scores the idea on margin, budget fit, capacity, skills and equipment, and market signal, and decides whether it is viable. An over-budget idea is never recommended, however good it looks.
3. **Compare and suggest.** Where it has market evidence, LaunchWise suggests an alternative and scores it with the same engine.
4. **Explain.** Claude explains the result in plain language. A post-check rejects any explanation that uses a number or source that is not in the result.
5. **Launch an example starter page.** After an explicit **Approve and publish** step, a simple page for the idea goes live at `launchwise.pro/s/<name>`, clearly marked as an example, with an unpublish link and a 7-day expiry.

It can also say "keep your original idea" or "nothing is viable yet". Honest answers are part of the design.

The demo scenario used throughout: a home bakery in Pune, ₹10,000 budget, about 3 cakes a day, weekends only. There "everyday cakes" barely pay and "custom celebration cakes" score higher, so the app recommends the pivot. Three other guided scenarios show the original idea winning, nothing being viable, and a Noida business with no market data (feasibility only).

## Market evidence (pilot: Pune home bakeries)
LaunchWise checks ideas against a small, hand-verified market dataset (`backend/app/data/market_opportunities.json`). The pilot has five Pune home-bakery entries on occasion-cake pricing, custom cake prices, festive demand, an online cake marketplace and shop rents. Sources are YourStory, Business Today, Housing.com and LBB Pune. Each entry records its source name, link, retrieval date, verification status and signal strength.

- **Evidence can support or argue against an option.** Pune shop rents, for example, count against opening a shopfront on a small budget.
- **Market signal is one of five scores (15% of the total),** so evidence informs the decision but never overrides budget, capacity or skills.
- **Suggestions come from the data.** When an idea is not viable, LaunchWise can suggest an alternative such as custom celebration cakes. Its price is taken from the cited source and every other figure is labelled as assumed.
- **Outside covered markets, it says so.** Any other city or category gets a feasibility-only check with a neutral market score and a clear statement that there is no market evidence there. Nothing is guessed.
- The dataset is built to grow city by city and category by category.

## How Claude powers LaunchWise
- **Understands the owner (Intake).** Turns a plain-language description (up to 1,500 characters) into a structured draft of the form: budget, prices, capacity, location. It flags what is missing for the owner to fill in instead of guessing, and nothing runs until the owner submits the form.
- **Explains every decision (Explain).** Writes a short explanation of each result, including why an idea fails and what a suggested alternative changes, grounded in the actual numbers and cited sources.
- **Built to be trusted with money decisions.** Everything Claude writes is verified before anyone sees it, user input is treated as untrusted, and calls have retries, safe fallbacks and usage limits. A deterministic engine does all the arithmetic, and a human approves before anything goes live, so owners get Claude's understanding without the risk of an invented figure.
- Text written by Claude carries a small notice: "Claude can make mistakes. Check the figures before you rely on them." The standard template explanation does not, because Claude did not write it.

## Honest numbers
Every figure is labelled as provided by you, calculated, taken from a source, or assumed. Assumptions are listed in the caveats shown with the result. Food businesses see an FSSAI registration note.

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

- **Engine** (`backend/app/engine/`): feasibility numbers (startup cost, margin, weekly capacity, break-even, budget check), each tagged with where it came from (`user_provided`, `derived`, `estimate`, `assumption`, `from_source`). Money is `Decimal`, never a float. The engine imports nothing that does I/O, and a test enforces that. Numbers come from Python, never from Claude.
- **Ranking** (`compare_strategies`): scores options on five dimensions (margin 30%, budget fit 20%, capacity 20%, skills and equipment 15%, market signal 15%), explains each score, and lists plain-language caveats (assumed inputs, weak or contrary evidence, missing skills or equipment).
- **Claude, in two places only** (model name from the `CLAUDE_MODEL` env var, never in code):
  - **Explain:** a post-check rejects the text if it uses a number that is not in the engine's results, names an unknown source, promises profit, misdescribes contrary evidence, or contains markup. It gets one retry, then a fixed template is used instead, and the response says which one it was.
  - **Intake:** its output is validated JSON; the visitor reviews and edits the draft.
  Claude outputs validated JSON or plain text only, never HTML or code. With no key set, or when call caps are spent (20 per visitor session, 500 overall, both configurable), the app falls back cleanly and still works.
- **Starter pages** (approval-guarded):
  1. **Preview:** the owner enters a business name, an optional description and email, and an offer (prefilled from the recommendation). The server renders the page from a business-agnostic `StorefrontConfig` template, with all text escaped, and requests an approval bound to the hash of that exact config. The preview shows in a fully sandboxed frame. Nothing is public.
  2. **Approve and publish:** the one explicit click grants the strategy and launch approvals server-side, each written to the audit log. The **deploy guard** then consumes the launch approval and refuses to run unless a matching one exists. The "deployer" stores the page.
  3. **Live:** every page carries `noindex` and an "Example page made with LaunchWise" banner and expires after 7 days. At most 50 are live and 3 can be published per visitor per hour. The owner gets a private unpublish link once, whose secret is kept after `#` so it is never sent to a server; only a hash of it is stored.
  4. Text rules: no HTML, links or images; the contact email is shown as plain text; a small whole-word blocklist is refused with fixed text.
  A seeded example page, `/s/example-pune-cakes`, is built at startup from the pivot scenario, never expires and cannot be unpublished through the public flow.
- **SQLite** on a Docker volume (`/data`): live pages, expiry, unpublish-token hashes, append-only page events and the approval audit log. Drafts and previews stay in memory. Audit records hold hashes, never page text, tokens or visitor addresses.
- **Contact form:** validation, honeypot, rate limits and header-injection protection, sent by SMTP. It is live on the deployed site; locally it is off by default (`CONTACT_ENABLED=false`, answers 503, no SMTP).

## Built on GoDaddy
- **Hosting:** a GoDaddy VPS (Ubuntu 24.04) running Docker Compose, with Caddy providing HTTPS.
- **Domain:** `launchwise.pro`; `www.` redirects to it.
- **Mail:** the contact form sends through a GoDaddy business mailbox over SMTP (`smtpout.secureserver.net`, port 465, SSL).
- **Logo:** created with GoDaddy Airo.
- The footer reads "Hosted on GoDaddy · Powered by Claude · Contact". Published starter pages are stored in the app's own database and served from our domain. Calling GoDaddy's domain and website APIs is listed under Next steps.

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
| `make check` | backend: `ruff check`, `ruff format --check`, `mypy`, `pytest` (about 1,850 tests) |
| `make test` | backend `pytest` only |
| `make check-frontend` | frontend: eslint, type check, vitest (over 410 tests) |
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
- **Contact form:** it is live on the deployed site. Locally it is off by default (`CONTACT_ENABLED=false`). To enable it, fill the `SMTP_*` and `CONTACT_RECIPIENT` values, set `CONTACT_ENABLED=true`, then `docker compose up -d --force-recreate backend`. If a value is missing or still an example, the app still starts and the form answers "not configured"; the startup log names the missing variables, never their values. The recipient is fixed in `.env`.
- **Limits are env-tunable** (see `.env.example`): contact (default 5 per visitor per hour, 200 per hour overall), analyze (60 per minute), publishing (`PUBLISH_LIMIT_PER_HOUR`, `MAX_LIVE_PAGES`), Claude call caps. Rate limits key on the real visitor address: Caddy sets `X-Forwarded-For` and the backend trusts it only from Caddy's fixed address.
- **Logs** hold outcomes only, never personal data: uvicorn runs with `--no-access-log` (do not remove it) and Caddy has no request log.
- **HSTS starts short** (`max-age=300`, no `includeSubDomains`, no `preload`) so a mistake is cheap to undo. Raise it in `frontend/Caddyfile` in steps once launch works.
- **Headers:** Caddy sets a Content-Security-Policy of `default-src 'self'; frame-ancestors 'none'` (no inline styles, which is why starter pages load their stylesheet from `/api/storefront/style.css`), plus `nosniff`, `X-Frame-Options: DENY`, a referrer policy and a permissions policy.
- **Network:** the compose network uses the fixed subnet `10.77.0.0/24`. It is a private range chosen to be unlikely to clash; if the VPS already uses it for another Docker network, change the subnet and Caddy's fixed address together in `docker-compose.yml` (`docker network ls` shows what exists).
- **Non-root ports:** Caddy binds 80 and 443 as an unprivileged user via the `net.ipv4.ip_unprivileged_port_start=0` sysctl. This works in local Docker and on the VPS, where the stack is live. If another host refuses the sysctl, fall back to `cap_add: [NET_BIND_SERVICE]` with `setcap` in `frontend/Dockerfile`.
- **Local smoke test of the full stack:** set `SITE_DOMAIN=localhost` in `.env`, run `docker compose up -d --build`, then `curl -k https://localhost/api/health` (`-k` because Caddy issues a local certificate).
- Base images are pinned to a version tag (`python:3.14-slim`, `node:24-alpine`, `caddy:2-alpine`), not to an image digest, so a rebuild can pick up newer patch releases.

## Design choices and current scope
- **Assumptions are labelled.** Weekly hours, time per item and the working-capital reserve may be estimated rather than given by the owner, and demand is modelled at 25%, 50% and 100% of capacity. Each is tagged `assumption` or `estimate` and listed in the caveats, so owners see exactly what is estimated.
- **The market dataset is a pilot.** It covers Pune home bakeries (five entries). Everything else gets an honest feasibility-only check.
- **The agent step log is a recorded replay.** The analysis is deterministic and finishes in one request; the app replays its recorded steps with a short animation, labelled "replay of recorded steps".
- **Guided scenarios use sample data.** Their inputs and prices are made up for the walkthrough and labelled so.
- **Starter pages are example pages.** They last 7 days, carry a banner, are hidden from search engines, take no orders or payments, and have no images or links. There are no accounts: the unpublish link is the owner's control.
- **Publishing is direct, with unpublish instead of rollback.** There is no previous-version history for pages yet.
- **Drafts live in memory; published pages persist in SQLite.** A restart loses unpublished previews, not live pages. The backend runs as a single worker, and rate limits are per process.
- **The blocklist is deliberately small.** It is a guard rail, not moderation.

## Next steps
- Full website publishing based on the owner's preferences.
- Domain suggestions with GoDaddy's domain API (and other GoDaddy domain and website APIs).
- More cities and business categories in the market dataset.
- A Hindi and English toggle, and seasonal offers.
- Page version history and rollback.

## Docs
`docs/SPEC.md` (behaviour of each part) and `docs/ENGINEERING.md` (engineering standards).
