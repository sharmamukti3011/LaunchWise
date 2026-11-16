# LaunchWise engineering standards (read on demand)

Execution is judged on code quality, design patterns, security patterns and engineering practice. Follow these, and keep the repo easy to inspect.

## Architecture and design patterns
- **Layering:** routes -> services -> engine. Route handlers only parse requests and call services. Business logic lives in services; pure calculations live in `engine/`.
- **Pure core:** the feasibility engine has no I/O, no DB, no LLM calls. Same inputs always give the same outputs.
- **Dependency injection:** pass the Claude client, mailer, deployer and clock into services instead of importing them globally. Tests replace them with fakes.
- **Tool registry:** each agent tool is one function with a Pydantic input model and a Pydantic output model, registered in one place. The orchestrator never calls code outside the registry.
- **State machine for approvals:** allowed transitions are defined in one table. Anything else raises an error.
- **Single settings module:** all configuration comes from env vars through one validated settings object. No `os.environ` calls scattered around the code.
- **Fail loudly at startup:** validate settings and the market dataset when the app starts.

## Security patterns
- **Secrets:** env vars only. `.env` is gitignored, `.env.example` has placeholders. Never log secrets. If a secret appears in a diff, stop and flag it.
- **Input validation at every boundary:** Pydantic models for requests, tool inputs and tool outputs. Reject and retry invalid Claude output, with a retry cap.
- **No LLM-generated code or HTML:** Claude produces JSON content only. Templates render it, and all text is escaped.
- **Approvals:** bound to a hash of the exact payload, single-use, checked server-side before deploy.
- **Contact form:** validation, rate limiting, honeypot field, header-injection protection. The recipient address is set server-side, never from the request.
- **SQL:** parameterized queries only.
- **HTTP:** HTTPS only, sensible CORS (allow only our own origin), security headers from the reverse proxy.
- **Containers and server:** non-root user, only ports 80 and 443 public, SQLite and internal ports not exposed, SSH keys only.
- **Abuse limits:** cap Claude calls per session and globally; rate limit public endpoints.
- **Logging:** structured logs with request IDs. No personal data or secrets.
- **Dependencies:** pin versions and avoid unneeded packages.

## Quality practices
- Type hints everywhere; small, single-purpose functions; comment the why, not the what.
- Money is `Decimal` or integer paise, never float.
- Consistent error handling: domain errors map to clear HTTP responses. No bare `except`.
- Tests first for the engine and approvals. Fake external services in tests. Cover edge cases listed in `docs/SPEC.md`.
- Add a health-check endpoint and use it to verify each deploy.
- Small commits with clear messages. Never commit failing tests, secrets or generated artifacts.

## Tooling (enforce with tools, not just prose)
- Backend: `ruff` (lint and format), `mypy` (types), `pytest`.
- Frontend: `eslint` and a TypeScript or type check.
- One command runs everything: `make check` (lint, types, tests). Run it before declaring any task done.
- Optional: a pre-commit hook that runs the fast checks.

## Operations
- Deploy flow: render to staging, promote on approval, keep the previous version, verify the live URL, roll back on failure.
- Before the demo: snapshot the SQLite file and `.env`, and confirm a clean-browser run works.

## Show it to the judges
- Keep a short README section, "Engineering and security decisions", listing the patterns above and pointing at the tests.
- Keep the audit log and approval flow visible in the product.