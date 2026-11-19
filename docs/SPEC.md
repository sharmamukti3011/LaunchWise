# LaunchWise spec (read on demand)

## Agent tools (Pydantic in/out for each)
- `extract_constraints(text)` -> ConstraintProfile
- `run_feasibility(profile, option)` -> FeasibilityResult (pure Python)
- `query_market_opportunities(location, category)` -> list of Opportunity
- `compare_strategies(profile, options)` -> ranked options; deterministic scores for margin, capacity, budget, skill/equipment fit, market signal
- `check_domain_availability(name)` -> real or labeled mock
- `generate_storefront_config(profile, strategy)` -> validated StorefrontConfig
- `request_approval(action, payload_hash)`
- `deploy_storefront(config_id)` -> refuses without a matching approval
- `verify_deployment(url)` -> HTTPS 200 plus content check

Behavior: the original idea is always an option; the agent can recommend keeping it and can reject an opportunity with an explanation; Claude names evidence by its source name (for example "market evidence from YourStory"), never by dataset ID, and the post-check rejects any source that is not in the response; every figure is tagged verified / user-provided / assumption / estimate; never promise profit; stream every tool call to the timeline.

## Feasibility engine
- Pure functions, no network/DB/LLM. The What-If simulator calls the same functions.
- Inputs: budget, units/day, days/week, variable cost per unit, price, fixed startup costs.
- Outputs: startup cost, unit variable cost, contribution margin (amount and %), weekly capacity, max weekly revenue, break-even under low/medium/high demand, budget check.
- Tests must cover: zero margin, negative margin, over budget, 1 unit/day, zero days available, very high price.

## Approvals
- States: DRAFT -> STRATEGY_PROPOSED -> STRATEGY_APPROVED -> LAUNCH_APPROVED -> DEPLOYING -> LIVE (or FAILED).
- An approval is bound to a hash of the exact payload; changed content invalidates it. Approvals are single-use.
- Audit log for every tool call and approval decision.
- Deploy: render to staging, promote to live on approval, keep the previous version for rollback, then verify.
- Storefronts are served at `/s/<slug>` on our own domain. No domain per business, no wildcard subdomains. Domain purchase for a generated business is an approval-gated mock. The real submission domain is bought manually.

## Market dataset (`backend/app/data/market_opportunities.json`)
- Lives inside `backend/app` on purpose: the backend image copies only that directory, so a file elsewhere would not ship. A deploy test checks it is in the build context and not excluded by `.dockerignore`.
- Loaded and validated at startup (the app refuses to boot on bad data). Shipped entries are `TODO(verify)` placeholders until a human replaces them; `make check-dataset` (not part of `make check`) fails while any entry has a `.invalid` source, a TODO marker or `unverified_sample` status. Run it before submission.
- 8-12 hand-curated Pune bakery opportunities, validated with Pydantic at startup.
- Fields: id, title, location, category, signal_summary, evidence, source_name, source_url, event_date, is_evergreen, retrieved_date, verification_status (verified / single_source / unverified_sample), verified_by, verified_on, signal_strength (low/medium/high), required_skills, required_equipment, lead_time_days, label.
- `is_evergreen` (bool, default false): `event_date` is required unless `is_evergreen` is true. Evergreen entries never expire.
- Past event dates are excluded from recommendations: a non-evergreen entry with a past date scores 0 on market signal and is non-viable (reason "event passed"). Include at least one opportunity the agent should reject. Use qualitative signal strength unless a source gives a figure. Never fabricate an event date.

## Analyze (`POST /api/analyze`)
- Input: constraint profile, a category, and 1-6 options (exactly one original; alternatives may link a dataset `opportunity_id`). Output: validated profile, feasibility numbers with source tags per option, ranked options, caveats, and an ordered deterministic step log (tool-style steps the streamed timeline can replay). No Claude calls, no SQLite.
- Any location and any business is accepted. Market evidence comes only from the dataset, never from the request. Coverage is matched tolerantly on place (trim, case-insensitive, `Pune, Maharashtra` is Pune) and on category (`home bakery` is a bakery).
- If the dataset has no coverage for the location or category: feasibility-only analysis. Return `market_coverage: "none"` with a plain-language message, the original option's numbers, source tags and caveats, no alternatives compared, and the original's market signal stays a neutral 50 labelled "no market evidence". The original may be recommended if it is viable. Never add market claims that are not in the dataset. An alternative's `opportunity_id` must still match a dataset entry.
- Limits: max 6 options, bounded field lengths and money, 32KB body (enforced by Caddy and by backend middleware), 60 requests per minute per client. Error bodies are generic and never echo submitted values; logs hold outcomes only, no personal data.
- `/s/<slug>` is served by the backend (Caddy proxies `/s/*`). See Starter pages below.

## Storefront and contact form
- Template renders brand, tagline, products, prices, availability, capacity note, contact form from StorefrontConfig. It is business-agnostic: no cake or bakery wording, so any business (a Noida high-protein breakfast service, say) can be approved and deployed the same way.
- Form: validate, rate limit, honeypot, prevent header injection, send to the Titan mailbox via SMTP with credentials from env vars. Test end to end on the real server early.

## Starter pages (`/s/<slug>`)
- Flow: preview (draft in memory, 30 minutes, approval requested for the exact config hash) -> "Approve and publish" -> live. One explicit publish click grants both approvals (strategy, then launch) server-side; each is audited. The DeployGuard consumes the launch approval and refuses without a matching one; the deployer stores the page.
- Durable in SQLite on the `launchwise-data` volume (`/data`, survives `docker compose up -d --build`; never `down -v`): live pages, expiry, a SHA-256 hash of each unpublish token (never the token), append-only page events (published, unpublished, unpublish_refused, expired, seeded) and the approval audit log. Page text is cleared when a page ends. Records hold hashes and a random page reference, never text, tokens or visitor addresses.
- Guardrails: noindex (header and meta) and an "Example page made with LaunchWise" banner on every page; 7-day expiry; name 60, description 300; plain text only (no HTML, links, images; the contact email is shown as text); a small whole-word blocklist, refused with fixed text; at most 50 live pages (`MAX_LIVE_PAGES`), 3 publishes per hour per client (`PUBLISH_LIMIT_PER_HOUR`); unpublish attempts are rate limited and every refusal looks the same.
- Unpublish link: `/#unpublish/<slug>/<token>`; the secret sits after `#`, so it is never sent to a server or logged, and the app removes it from the address bar once read. Shown once at publish time.
- Example page: `/s/example-pune-cakes`, seeded at startup if missing from the pivot scenario's recommendation, made-up business name, never expires, no token, cannot be unpublished through the public flow, keeps the banner and noindex, not counted toward the cap.

## Reliability and security
- Validate all Claude output with Pydantic; retry on invalid output with a cap.
- Cap Claude calls per session and globally; keep a cached known-good run as fallback.
- Containers run as non-root; only ports 80 and 443 exposed; SQLite and internal ports not exposed.
- "Run guided demo" button with the seeded Pune scenario.

## Submission checklist (pass/fail)
1. Developer account and `gdd` CLI working.
2. Customer ID and hosting choice (VPS) submitted.
3. App deployed on the VPS.
4. Own domain bought and pointed at the app.
5. HTTPS works.
6. Titan mailbox created, test email received.
7. Contact form delivers to the mailbox.
8. Mailbox password not in code or repo.

## Done means
Public HTTPS URL works; contact form reaches the mailbox; guided demo runs in under 3 minutes; engine numbers reproducible and tested; deploy impossible without a matching approval; one scenario recommends keeping the original idea and one rejects an opportunity; no secrets in repo history; README covers setup and architecture.