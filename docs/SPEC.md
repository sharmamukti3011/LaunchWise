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

Behavior: the original idea is always an option; the agent can recommend keeping it and can reject an opportunity with an explanation; Claude cites dataset IDs; every figure is tagged verified / user-provided / assumption / estimate; never promise profit; stream every tool call to the timeline.

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

## Market dataset (`data/market_opportunities.json`)
- 8-12 hand-curated Pune bakery opportunities, validated with Pydantic at startup.
- Fields: id, title, location, category, signal_summary, evidence, source_name, source_url, event_date, retrieved_date, verification_status (verified / single_source / unverified_sample), verified_by, verified_on, signal_strength (low/medium/high), required_skills, required_equipment, lead_time_days, label.
- Past event dates are excluded from recommendations. Include at least one opportunity the agent should reject. Use qualitative signal strength unless a source gives a figure. Never fabricate an event date.

## Storefront and contact form
- Template renders brand, tagline, products, prices, availability, capacity note, contact form from StorefrontConfig.
- Form: validate, rate limit, honeypot, prevent header injection, send to the Titan mailbox via SMTP with credentials from env vars. Test end to end on the real server early.

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