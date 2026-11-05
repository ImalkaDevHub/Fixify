.PHONY: api worker web test web-test lint typecheck migrate

api:
	cd services/api && python -m app.serve

worker:
	cd services/api && python -m app.worker

web:
	cd apps/web && npm run dev

migrate:
	cd services/api && alembic upgrade head

test:
	cd services/api && pytest

web-test:
	cd apps/web && npm test

lint:
	cd services/api && ruff check . && cd ../../apps/web && npm run lint

typecheck:
	cd apps/web && npm run typecheck
