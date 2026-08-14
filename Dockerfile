# Slim, single-stage: this is one Python process with three dependencies.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Tashkent

WORKDIR /app

# CA certificates matter here: the bot talks to api.telegram.org and
# api.anthropic.com, and truststore reads the system store.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates tzdata fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
# Wholesale, with .dockerignore deciding what stays out. Listing files one by
# one is how the media library came to be missing from the image.
COPY data ./data
COPY .claude/skills/humanize-uz ./.claude/skills/humanize-uz

# The voice guide, knowledge base and backup pool are read at runtime, so a
# missing or empty copy degrades output silently instead of crashing. Fail the
# build instead.
#
# The pool is COUNTED rather than checked for bytes: "posts: []" is a perfectly
# non-empty file and sails past `test -s`, which would ship a bot whose only
# safety net against an unapproved slot is nothing at all.
RUN test -f .claude/skills/humanize-uz/SKILL.md \
 && test -f data/knowledge/models.yaml \
 && test -s data/media_library.yaml \
 && python -c "import yaml,sys; n=len((yaml.safe_load(open('data/backup_pool.yaml',encoding='utf-8')) or {}).get('posts') or []); a=len((yaml.safe_load(open('data/media_library.yaml',encoding='utf-8')) or {}).get('assets') or []); print('backup pool:', n, 'posts;', a, 'assets'); sys.exit(0 if n >= 3 and a >= 1 else 1)"

# /app/data is read-only content from the image; /app/state is the volume.
RUN useradd -m -u 10001 bot && mkdir -p /app/state && chown -R bot:bot /app
USER bot

HEALTHCHECK --interval=60s --timeout=20s --start-period=30s --retries=3 \
  CMD python -m app --preflight --db /app/state/bot.db || exit 1

CMD ["python", "-m", "app", "--db", "/app/state/bot.db"]
