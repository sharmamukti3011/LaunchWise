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

## Engineering and security decisions
TODO: to be written.
