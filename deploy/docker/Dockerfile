FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    IRA_RUNTIME_ROOT=/srv/ira

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY resources ./resources
COPY config/api_keys.example.json config/watchlist.json ./config/
RUN pip install --no-cache-dir -e .

RUN useradd --create-home --uid 10001 ira && mkdir -p /srv/ira && chown -R ira:ira /app /srv/ira
USER ira

VOLUME ["/srv/ira"]
ENTRYPOINT ["ira-mcp"]
