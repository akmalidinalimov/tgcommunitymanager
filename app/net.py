"""Shared outbound HTTP setup.

This developer machine sits behind a TLS-intercepting proxy whose CA OpenSSL
rejects, so neither Python's default context nor certifi's bundle can verify
api.telegram.org or api.anthropic.com. ``truststore`` delegates verification to
the operating system's own store — the same path curl uses, which is why curl
worked when Python did not.

Verification stays ON. This repairs the trust path; it never bypasses it. On a
Linux VPS the identical code simply uses the system store.

Every outbound client in the project builds from here, so the fix exists once
rather than being rediscovered per SDK.
"""

from __future__ import annotations

import ssl

import httpx
import truststore


def ssl_context() -> ssl.SSLContext:
    """An SSL context that trusts the OS certificate store."""
    return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


def http_client(*, timeout: float = 60.0) -> httpx.Client:
    """A synchronous httpx client wired to the OS trust store."""
    return httpx.Client(verify=ssl_context(), timeout=timeout)
