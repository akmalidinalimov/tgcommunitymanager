# Slim, single-stage: this is one Python process with three dependencies.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Tashkent

WORKDIR /app

# CA certificates matter here: the bot talks to api.telegram.org and
# api.anthropic.com, and truststore reads the system store.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates tzdata \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY data/knowledge ./data/knowledge
COPY data/backup_pool.yaml ./data/backup_pool.yaml
COPY .claude/skills/humanize-uz ./.claude/skills/humanize-uz

# The voice guide and knowledge base are read at runtime, so a missing copy
# would degrade output silently rather than crashing. Fail the build instead.
RUN test -f .claude/skills/humanize-uz/SKILL.md \
 && test -f data/knowledge/models.yaml \n && test -s data/backup_pool.yaml

RUN useradd -m -u 10001 bot && mkdir -p /app/data && chown -R bot:bot /app
USER bot

HEALTHCHECK --interval=60s --timeout=20s --start-period=30s --retries=3 \
  CMD python -m app --preflight || exit 1

CMD ["python", "-m", "app"]
