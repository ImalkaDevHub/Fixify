.PHONY: api worker web test lint typecheck

api:
	cd services/api && uvicorn app.main:app --reload

worker:
	cd services/api && python -m app.worker

web:
	cd apps/web && npm run dev

test:
	cd services/api && pytest

lint:
	cd apps/web && npm run lint

typecheck:
	cd apps/web && npm run typecheck
