# syntax=docker/dockerfile:1
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps for asyncpg / bcrypt builds
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# entrypoint waits for DB, runs migrations + seed, then boots uvicorn.
# Strip any CR (Windows clones may introduce CRLF) so the shebang resolves,
# then make executable. Invoke via bash to be doubly safe across checkouts.
RUN sed -i 's/\r$//' ./entrypoint.sh && chmod +x ./entrypoint.sh
CMD ["bash", "./entrypoint.sh"]
