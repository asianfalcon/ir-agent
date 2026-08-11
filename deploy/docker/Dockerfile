FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ALPHASONAR_RUNTIME_ROOT=/srv/alphasonar \
    PATH=/app/.venv/bin:$PATH

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY resources ./resources
COPY config/api_keys.example.json config/watchlist.json ./config/
RUN pip install --no-cache-dir uv \
    && uv sync --frozen --no-dev

RUN useradd --create-home --uid 10001 alphasonar \
    && mkdir -p /srv/alphasonar \
    && chown -R alphasonar:alphasonar /app /srv/alphasonar
USER alphasonar

VOLUME ["/srv/alphasonar"]
CMD ["alpha-mcp"]
