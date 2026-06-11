FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY . .

CMD alembic upgrade head && \
    python -m app.seed && \
    python -m app.graph.ingest && \
    python -m app.graph.snap && \
    python -m app.surveillance.ingest && \
    python -m app.surveillance_seed && \
    uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
