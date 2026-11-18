# LaunchWise
The Market-Aware Business Builder

## Overview
LaunchWise helps first-time entrepreneurs turn an idea into a live business. You give it an idea and real constraints (budget, capacity, hours). It compares business options using deterministic feasibility math and a sourced market dataset, recommends one (or keeping your original idea), and after your approval deploys a storefront.

Demo scenario: a home bakery in Pune, ₹10,000 budget, about 3 cakes per day, weekends only.

## Setup
Requires Python 3.11+ and Node.js.

```bash
cp .env.example .env     # then fill in real values; .env is gitignored
make venv                # create .venv and install pinned backend deps
make check               # ruff, mypy, pytest
make run-backend         # http://localhost:8000/api/health
```

Frontend:

```bash
cd frontend && npm install
make run-frontend        # http://localhost:5173
make check-frontend      # eslint and type check
```

## Deployment
The stack is two containers, both running as non-root users: **Caddy** (automatic HTTPS, `www` redirect to the root domain, serves the built frontend, proxies `/api` and `/s/<slug>` to the backend) and the **backend**. Only ports 80 and 443 are public; the backend publishes nothing.

On the Ubuntu 24.04 VPS, with Docker and Compose installed and DNS A records for `launchwise.pro` and `www.launchwise.pro` pointing at the server:

```bash
git clone <repo> && cd LaunchWise
cp .env.example .env && chmod 600 .env   # fill in real values; this file never leaves the server
docker compose up -d --build
curl -fsS https://launchwise.pro/api/health
```

- **Secrets** live only in the server-side `.env`, loaded through `env_file`. They are not in the repo, the images, or the compose file.
- **Contact form** is off until you set `CONTACT_ENABLED=true`. The Titan SMTP values stay placeholders until verified (`TODO(verify)` in `.env.example`).
- **Certificates** are kept in the `caddy-data` volume. Do not run `docker compose down -v`, or the next start re-requests them and can hit Let's Encrypt rate limits.
- **HSTS starts short** (`max-age=300`, no `includeSubDomains`, no `preload`) so a mistake is cheap to undo. Once launch works, raise it in `frontend/Caddyfile` in steps (a day, a week, then months). Add `includeSubDomains` only if every subdomain serves HTTPS, and `preload` only as a deliberate, hard-to-reverse choice.
- **Content-Security-Policy** is `default-src 'self'`. Loosen it if the storefront template needs inline styles or external assets.
- **Network:** the compose network uses the fixed subnet `10.77.0.0/24` so the backend can trust proxy headers from Caddy's address only. `TODO(verify)`: make sure it doesn't clash with another network on the VPS.
- **Non-root ports:** Caddy binds 80 and 443 as an unprivileged user through the `net.ipv4.ip_unprivileged_port_start=0` sysctl in `docker-compose.yml`. This worked locally (Docker 29 on Colima). `TODO(verify)` on the VPS. If the host refuses the sysctl, fall back to `cap_add: [NET_BIND_SERVICE]` with `setcap cap_net_bind_service=+ep /usr/bin/caddy` in `frontend/Dockerfile` and remove `no-new-privileges` from the caddy service only (it blocks file capabilities). Caddy stays non-root either way.
- **Local smoke test:** set `SITE_DOMAIN=localhost` in `.env`, run `docker compose up -d --build`, then use `curl -k https://localhost/api/health` (Caddy issues a local certificate, hence `-k`).

## Engineering and security decisions
TODO: to be written.
