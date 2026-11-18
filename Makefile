VENV := .venv
BIN := $(VENV)/bin
BACKEND := backend

.PHONY: venv check test fmt run-backend run-frontend check-frontend check-dataset

venv:
	python3 -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -r $(BACKEND)/requirements.txt -r $(BACKEND)/requirements-dev.txt

check:
	cd $(BACKEND) && ../$(BIN)/ruff check .
	cd $(BACKEND) && ../$(BIN)/ruff format --check .
	cd $(BACKEND) && ../$(BIN)/mypy .
	cd $(BACKEND) && ../$(BIN)/pytest

test:
	cd $(BACKEND) && ../$(BIN)/pytest

fmt:
	cd $(BACKEND) && ../$(BIN)/ruff format .

run-backend:
	cd $(BACKEND) && ../$(BIN)/uvicorn app.main:create_app --factory --reload --port 8000

run-frontend:
	cd frontend && npm run dev

check-frontend:
	cd frontend && npm run lint && npm run typecheck && npm test

# Run before submission, not part of `make check`: fails while the dataset still holds placeholders.
check-dataset:
	cd $(BACKEND) && ../$(BIN)/python scripts/check_dataset.py
