FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    API_HOST=0.0.0.0 \
    API_PORT=8000
WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic

RUN pip install --no-cache-dir . \
    && useradd --system --uid 10001 --no-create-home fixify \
    && mkdir -p /artifacts && chown fixify /artifacts

# The API never launches a browser and needs no elevated privileges.
USER fixify
EXPOSE 8000
CMD ["python", "-m", "app.serve"]
