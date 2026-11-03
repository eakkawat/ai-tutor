.PHONY: setup test lint dev web start
setup:  ## create .venv (Python 3.12) and install deps
	uv sync
	cd web && npm install
test:   ## backend and frontend unit tests
	uv run pytest -q
	cd web && npm test
lint:
	uv run ruff check .
dev:    ## API on http://127.0.0.1:8000
	uv run uvicorn ai_tutor.web.app:app --host 127.0.0.1 --port 8000 --reload
web:    ## frontend dev server on http://127.0.0.1:5173
	cd web && npm run dev
start:  ## API and frontend together; open http://127.0.0.1:5173. Ctrl-C stops both
	@trap 'trap - INT TERM EXIT; kill 0' INT TERM EXIT; \
	uv run uvicorn ai_tutor.web.app:app --host 127.0.0.1 --port 8000 --reload & \
	(cd web && npm run dev) & \
	wait
