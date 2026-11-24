PY ?= .venv/bin/python
export LOKY_MAX_CPU_COUNT ?= 4

.PHONY: setup data validate train report rag test lint serve all docker-up docker-down

setup:            ## create the virtualenv and install everything
	python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt

data:             ## rebuild marts + map from ../motor_insurance_risk_raw.csv and ../Dataset (local only)
	$(PY) -m pipeline.build_marts
	$(PY) -m pipeline.build_geo

validate:         ## data contracts
	$(PY) -m pipeline.validate

train: validate   ## train, gate, register + anomaly model + drift check
	$(PY) -m ml.regionalklasse
	$(PY) -m ml.anomaly
	$(PY) -m ml.drift

report:           ## computed findings -> reports/analysis.md, data/marts/insights.json
	$(PY) -m pipeline.report

rag:              ## rebuild the retrieval index (needs ../PDFs for PDF chunks)
	$(PY) -m rag.index

test:
	$(PY) -m pytest

lint:
	.venv/bin/ruff check .

serve:
	$(PY) -m uvicorn app.main:app --reload --port 8000

all: data train report rag lint test

docker-up:
	docker compose up -d --build

docker-down:
	docker compose down
