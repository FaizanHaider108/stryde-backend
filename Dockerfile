FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini .
COPY migrations ./migrations
COPY app ./app
COPY scripts ./scripts

RUN mkdir -p uploads && chmod +x scripts/docker_entrypoint.sh

ENV UVICORN_HOST=0.0.0.0
ENV UVICORN_PORT=8000
ENV APP_ROOT=/app

EXPOSE 8000

# Use shell form so PORT from Render is honored; prepare_db.py fixes DuplicateTable deploys.
CMD sh scripts/docker_entrypoint.sh
