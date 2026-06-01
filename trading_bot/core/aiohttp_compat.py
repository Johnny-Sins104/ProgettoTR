"""Compatibility helpers for importing aiohttp in the bundled Windows runtime."""
from __future__ import annotations

import os
import ssl
from typing import Any


def install_aiohttp_windows_ssl_context_compat() -> None:
    """Avoid the bundled Windows OpenSSL Applink crash during aiohttp import.

    The bundled Python runtime can import ``ssl`` and create bare SSL contexts,
    but ``ssl.create_default_context()`` aborts the process with an OpenSSL
    Uplink error.  aiohttp creates default contexts at import time, so install a
    narrowly compatible replacement before importing aiohttp.
    """
    if os.name != "nt":
        return
    if getattr(ssl.create_default_context, "_progettotr_aiohttp_compat", False):
        return

    def _create_default_context(
        purpose: ssl.Purpose = ssl.Purpose.SERVER_AUTH,
        *,
        cafile: str | None = None,
        capath: str | None = None,
        cadata: str | bytes | None = None,
    ) -> ssl.SSLContext:
        if purpose == ssl.Purpose.SERVER_AUTH:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.verify_mode = ssl.CERT_REQUIRED
            context.check_hostname = True
        else:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE

        if cafile or capath or cadata:
            context.load_verify_locations(cafile=cafile, capath=capath, cadata=cadata)
        else:
            context.load_default_certs(purpose)
        return context

    setattr(_create_default_context, "_progettotr_aiohttp_compat", True)
    ssl.create_default_context = _create_default_context  # type: ignore[assignment]

