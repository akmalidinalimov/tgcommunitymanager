"""Deploy to Hostinger VM 1411263 via the API. No SSH, matching how freelanceai ships.

    python deploy/deploy.py            # deploy
    python deploy/deploy.py --check    # show what would be sent, send nothing

Secrets are read from .env and .mcp.json and go straight into the request body.
They are never printed, never passed as command arguments, and never echoed — a
credential in a terminal is a credential in a scrollback buffer.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.net import http_client  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
VM_ID = 1411263
PROJECT = "tgcommunitymanager"
API = f"https://developers.hostinger.com/api/vps/v1/virtual-machines/{VM_ID}/docker"

REQUIRED = (
    "TELEGRAM_BOT_TOKEN", "TELEGRAM_BOT_USERNAME", "TELEGRAM_CHANNEL_ID",
    "TELEGRAM_DISCUSSION_GROUP_ID", "TELEGRAM_CHANNEL_USERNAME",
    "TELEGRAM_ADMIN_CHAT_ID", "TELEGRAM_APPROVER_IDS", "ANTHROPIC_API_KEY",
)

#: Forwarded when present, and not an error when absent. The bot runs on
#: Anthropic alone; these only matter once REPLY_MODEL/OPENAI_MODEL names a GPT.
#: Absent from .env they must still reach compose as empty strings, because an
#: unset variable there makes Docker warn and substitute nothing — and the
#: preflight that catches a missing key can only catch it if it is missing
#: rather than stale.
OPTIONAL = ("OPENAI_API_KEY", "REPLY_MODEL", "OPENAI_MODEL")

#: Hostinger caps the compose `content` field. freelanceai hit this at 8312.
COMPOSE_CAP = 8192


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip().lstrip("﻿")
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip("\"'")
    return values


def minify_compose(text: str) -> str:
    """Strip full-line comments and collapse blank runs.

    The repo file keeps its documentation; only the API payload is minified.
    Inline comments are left alone, which is safer around YAML strings.
    """
    out: list[str] = []
    prev_blank = False
    for line in text.splitlines():
        if re.match(r"^\s*#", line):
            continue
        blank = not line.strip()
        if blank and prev_blank:
            continue
        out.append(line)
        prev_blank = blank
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="validate and print, send nothing")
    args = parser.parse_args()

    env = read_env(ROOT / ".env")
    missing = [k for k in REQUIRED if not env.get(k)]
    if missing:
        print(f"missing from .env: {', '.join(missing)}", file=sys.stderr)
        return 1

    mcp = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
    token = (mcp.get("mcpServers", {}).get("hostinger", {}).get("env", {})
             .get("HOSTINGER_API_TOKEN"))
    if not token:
        print("HOSTINGER_API_TOKEN not found in .mcp.json", file=sys.stderr)
        return 1

    compose = minify_compose((ROOT / "deploy" / "docker-compose.yml").read_text(encoding="utf-8"))
    if len(compose) > COMPOSE_CAP:
        print(f"compose is {len(compose)} chars, over Hostinger's {COMPOSE_CAP} cap", file=sys.stderr)
        return 1

    forwarded = REQUIRED + OPTIONAL
    environment = "\n".join(f"{k}={env.get(k, '')}" for k in forwarded)

    print(f"project    : {PROJECT}   (named explicitly — smmuzbot and freelanceai untouched)")
    print(f"vm         : {VM_ID}")
    print(f"compose    : {len(compose)} chars (cap {COMPOSE_CAP})")
    chosen = env.get("REPLY_MODEL") or env.get("OPENAI_MODEL") or "claude-opus-5"
    print(f"env vars   : {len(forwarded)} forwarded, values not shown")
    print(f"model      : {chosen}")
    if args.check:
        print("\n--check: nothing sent")
        return 0

    body = {"project_name": PROJECT, "content": compose, "environment": environment}
    with http_client(timeout=120.0) as client:
        response = client.post(
            API,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            json=body,
        )

    if response.status_code >= 400:
        # Never echo the request body — it carries every secret.
        print(f"\ndeploy failed: HTTP {response.status_code}", file=sys.stderr)
        print(response.text[:600], file=sys.stderr)
        return 1

    result = response.json()
    print(f"\ndeploy submitted: id={result.get('id')} state={result.get('state')}")
    print("Hostinger sometimes creates containers without starting them; if the project "
          "shows 'created' rather than 'running', call project start.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
