"""
http_clients.py
---------------
Module-level singleton httpx.AsyncClient per microservice.

One persistent client per service avoids re-creating a connection pool and
performing a fresh TCP handshake on every pipeline node invocation.
HTTP/1.1 keep-alive means subsequent requests reuse the open socket.

Clients are initialised lazily on first call (safe — httpx defers transport
init until the first request, so no event-loop is required at import time).
"""
from typing import Optional
import httpx

_heimdall: Optional[httpx.AsyncClient] = None
_aria:     Optional[httpx.AsyncClient] = None
_sage:     Optional[httpx.AsyncClient] = None
_valkyrie: Optional[httpx.AsyncClient] = None
_spyder:   Optional[httpx.AsyncClient] = None
_raven:    Optional[httpx.AsyncClient] = None

_LIMITS = httpx.Limits(max_keepalive_connections=5, max_connections=10)


def get_heimdall_client() -> httpx.AsyncClient:
    global _heimdall
    if _heimdall is None:
        _heimdall = httpx.AsyncClient(
            base_url="http://localhost:8001", timeout=10.0, limits=_LIMITS
        )
    return _heimdall


def get_aria_client() -> httpx.AsyncClient:
    global _aria
    if _aria is None:
        _aria = httpx.AsyncClient(
            base_url="http://localhost:8002", timeout=60.0, limits=_LIMITS
        )
    return _aria


def get_sage_client() -> httpx.AsyncClient:
    global _sage
    if _sage is None:
        _sage = httpx.AsyncClient(
            base_url="http://localhost:8003", timeout=120.0, limits=_LIMITS
        )
    return _sage


def get_valkyrie_client() -> httpx.AsyncClient:
    global _valkyrie
    if _valkyrie is None:
        _valkyrie = httpx.AsyncClient(
            base_url="http://localhost:8004", timeout=120.0, limits=_LIMITS
        )
    return _valkyrie


def get_spyder_client() -> httpx.AsyncClient:
    global _spyder
    if _spyder is None:
        _spyder = httpx.AsyncClient(
            base_url="http://localhost:8005", timeout=180.0, limits=_LIMITS
        )
    return _spyder


def get_raven_client() -> httpx.AsyncClient:
    global _raven
    if _raven is None:
        _raven = httpx.AsyncClient(
            base_url="http://localhost:8006", timeout=120.0, limits=_LIMITS
        )
    return _raven
