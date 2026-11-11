.PHONY: install doctor setup dev api web build test e2e ui docker docker-up docker-down docker-test

install:          ## install everything: LibreOffice, Poppler, fonts, Python env, web UI (then self-check)
	./scripts/install.sh

doctor:           ## check LibreOffice, Poppler, web UI and a test preview render
	.venv/bin/pitchcraft doctor

setup:            ## install Python and web dependencies only (system packages already installed)
	uv venv -q .venv && uv pip install --python .venv/bin/python -e ".[dev]"
	cd frontend && npm ci

api:              ## backend on :8600
	.venv/bin/pitchcraft serve --port 8600 --data data

web:              ## Next.js dev server on :3600 (proxies /api to :8600)
	cd frontend && npm run dev

dev:              ## both, for development
	$(MAKE) -j2 api web

build:            ## static web build served by the backend at :8600
	cd frontend && npm run build

test:             ## offline tests (no API key needed)
	.venv/bin/python -m pytest -q

ui:               ## browser walk-through of every screen (needs a running server and a user)
	.venv/bin/python tests/ui_smoke.py http://127.0.0.1:8600 $(USER_NAME) $(USER_PASS) ui_shots

e2e:              ## live test with Claude (needs ANTHROPIC_API_KEY and private/fixtures)
	PYTHONPATH=. .venv/bin/python private/scripts/e2e_live.py e2e_data

docker:           ## build the Docker image
	docker build -t pitchcraft .

docker-up:        ## run with Docker Compose on http://127.0.0.1:8600
	docker compose up -d --build

docker-down:      ## stop the Compose stack (data volume is kept)
	docker compose down

docker-test:      ## run the offline tests inside the image
	docker build --target test -t pitchcraft:test .
