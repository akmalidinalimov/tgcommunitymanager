"""Thin Bot API transport.

TLS note: this machine sits behind a TLS-intercepting proxy whose CA OpenSSL
rejects ("Basic Constraints of CA cert not marked critical"), so neither the
default context nor certifi's bundle can verify api.telegram.org. ``truststore``
delegates verification to the OS store, which is why curl works and Python did
not. Verification stays ON — this fixes the trust path rather than bypassing it.
On a Linux VPS the same code path is correct and simply uses the system store.
"""

from __future__ import annotations

import ssl
from typing import Any

import httpx
import truststore


class TelegramError(RuntimeError):
    """A non-ok response from the Bot API, carrying Telegram's own description."""

    def __init__(self, method: str, description: str, error_code: int | None = None,
                 retry_after: int | None = None):
        self.method = method
        self.description = description
        self.error_code = error_code
        self.retry_after = retry_after
        super().__init__(f"{method}: {description} (error_code={error_code})")


def _ssl_context() -> ssl.SSLContext:
    return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


class BotAPI:
    """Synchronous Bot API client, scoped to setup and smoke tests.

    The production runtime is async; the logic worth testing lives in pure
    functions elsewhere, so this stays deliberately small.
    """

    def __init__(self, token: str, *, timeout: float = 30.0):
        self._base = f"https://api.telegram.org/bot{token}/"
        self._client = httpx.Client(verify=_ssl_context(), timeout=timeout)

    def __enter__(self) -> "BotAPI":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def call(self, method: str, **params: Any) -> Any:
        """Invoke a Bot API method, raising TelegramError on a non-ok response."""
        payload = {k: v for k, v in params.items() if v is not None}
        response = self._client.post(self._base + method, json=payload)
        try:
            body = response.json()
        except Exception:  # pragma: no cover - malformed response
            raise TelegramError(method, f"non-JSON response: {response.text[:200]}")

        if not body.get("ok"):
            params_block = body.get("parameters") or {}
            raise TelegramError(
                method,
                body.get("description", "unknown error"),
                error_code=body.get("error_code"),
                retry_after=params_block.get("retry_after"),
            )
        return body.get("result")

    # --- the handful of methods this project actually uses -------------------

    def get_me(self) -> dict:
        return self.call("getMe")

    def get_chat(self, chat_id: int | str) -> dict:
        return self.call("getChat", chat_id=chat_id)

    def get_chat_member(self, chat_id: int | str, user_id: int) -> dict:
        return self.call("getChatMember", chat_id=chat_id, user_id=user_id)

    def send_message(
        self,
        chat_id: int | str,
        text: str,
        *,
        reply_to_message_id: int | None = None,
        parse_mode: str | None = None,
        disable_notification: bool | None = None,
    ) -> dict:
        """Send a message.

        ``reply_to_message_id`` is expressed via ``reply_parameters`` because it
        is the ONLY mechanism that places a message inside a comment thread.
        Passing ``message_thread_id`` instead is silently ignored by Telegram and
        the message lands in the group's main feed in front of everyone.
        """
        reply_parameters = (
            {"message_id": reply_to_message_id} if reply_to_message_id is not None else None
        )
        return self.call(
            "sendMessage",
            chat_id=chat_id,
            text=text,
            parse_mode=parse_mode,
            reply_parameters=reply_parameters,
            disable_notification=disable_notification,
        )

    def delete_message(self, chat_id: int | str, message_id: int) -> bool:
        return self.call("deleteMessage", chat_id=chat_id, message_id=message_id)

    def get_updates(
        self,
        *,
        offset: int | None = None,
        timeout: int = 25,
        allowed_updates: list[str] | None = None,
    ) -> list[dict]:
        return self.call(
            "getUpdates",
            offset=offset,
            timeout=timeout,
            allowed_updates=allowed_updates,
        )
