# LaunchWise

Agentic business builder for first-time entrepreneurs (hackathon project, deadline 20 Nov 2026). Takes an idea plus real constraints (budget, capacity, hours), compares business options using deterministic feasibility math and a sourced market dataset, recommends one (or keeping the original idea), and after human approval deploys a live storefront to a GoDaddy VPS.

Judged on Impact 35%, Demo 35%, Tech Usage 15%, Execution 15% (code quality, security). Judges will use the live link without us, so it must be self-explanatory and robust.

Demo scenario, used everywhere: home bakery in Pune, ₹10,000 budget, about 3 cakes per day, weekends only. Always Pune and ₹.

## Rules
- Numbers come from tested, deterministic Python, never from Claude. Claude extracts, interprets and explains.
- Approvals are enforced in the backend. Deploy must refuse to run without a matching approval.
- Claude outputs validated JSON content only, never HTML or code. A template renders the storefront; escape all text.
- No secrets in the repo. Use env vars, keep `.env` gitignored, commit `.env.example` only.
- Never invent GoDaddy API/CLI/SMTP details or market data. Mark unknowns `TODO(verify)` and ask me.
- Label anything mocked as simulated.
- Money uses Decimal or integer paise, never floats.

## Stack
Python 3.11+, FastAPI, Pydantic v2, SQLite; React + Tailwind; Docker Compose on a GoDaddy VPS behind a reverse proxy; one Claude orchestrator via the Anthropic API (model name from env var `CLAUDE_MODEL`, never hard-coded).

## Commands
- Run backend: `make run-backend` (uvicorn with the app factory: `app.main:create_app --factory`, port 8000).
- Run frontend: `make run-frontend` (Vite on 5173, proxies `/api` to the backend).
- Run tests: `make test` (backend `pytest`).
- Check backend: `make check` (ruff check, ruff format --check, mypy, pytest).
- Check frontend: `make check-frontend` (eslint and type check).
- `docker compose up`: not created yet; add when it exists.

## Scope
- In: home bakery only; feasibility engine, market comparison, What-If simulator, approval flow, template storefront, VPS deploy, contact form to Titan mailbox, guided demo mode.
- Out (do not build or suggest): cron monitoring, news scraping, SEO/blog publishing, payments, user accounts, multi-agent, multiple verticals, free-form LLM-generated HTML.
- Future scope (demo talk only): Hindi/English toggle, trend-based seller offers.

## How to work
- For tasks touching several files, propose a short plan first and wait for my go-ahead.
- Small steps, tests alongside code, commit after each working step.
- Before finishing: run tests, check the diff for secrets, summarize what changed.
- If something is ambiguous, pick the simplest option, state it in one line, and continue. Ask only on real blockers.

## Detailed specs
Read `docs/SPEC.md` when working on agent tools, approvals, the market dataset, storefront deploy, the contact form, or the submission checklist.

## Quality
- Layering: routes -> services -> engine. No business logic in route handlers.
- Pydantic models at every boundary; type hints everywhere.
- Validate all input and all Claude output; escape rendered text; parameterized SQL only.
- Inject external clients (Claude, mail, GoDaddy) so tests can fake them.
- Run `make check` before declaring a task done.
- Details in docs/ENGINEERING.md.