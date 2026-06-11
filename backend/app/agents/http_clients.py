"""
http_clients.py
---------------
Module-level singleton httpx.AsyncClient per microservice.

One persistent client per service avoids re-creating a connection pool and
performing a fresh TCP handshake on every pipeline node invocation.
HTTP/1.1 keep-alive means subsequent requests reuse the open socket.

Clients are initialised lazily on first call (safe — httpx defers transport
init until the first request, so no event-loop is required at import time).

Base URLs are read from environment variables so the same code works both
locally (defaults to localhost:800X) and under Docker Compose / Kubernetes,
where each agent is reached by its service name:

    HEIMDALL_URL=http://heimdall:8001
    ARIA_URL=http://aria:8002
    SAGE_URL=http://sage:8003
    VALKYRIE_URL=http://valkyrie:8004
    SPYDER_URL=http://spyder:8005
    RAVEN_URL=http://raven:8006
    DATAFLOW_URL=http://dataflow:8007
"""
import os
from typing import Optional
import httpx

_heimdall:  Optional[httpx.AsyncClient] = None
_aria:      Optional[httpx.AsyncClient] = None
_sage:      Optional[httpx.AsyncClient] = None
_valkyrie:  Optional[httpx.AsyncClient] = None
_spyder:    Optional[httpx.AsyncClient] = None
_raven:     Optional[httpx.AsyncClient] = None
_dataflow:  Optional[httpx.AsyncClient] = None

_LIMITS = httpx.Limits(max_keepalive_connections=5, max_connections=10)

# Base URLs — overridable via env; default to localhost for non-container runs.
HEIMDALL_URL  = os.getenv("HEIMDALL_URL",  "http://localhost:8001")
ARIA_URL      = os.getenv("ARIA_URL",      "http://localhost:8002")
SAGE_URL      = os.getenv("SAGE_URL",      "http://localhost:8003")
VALKYRIE_URL  = os.getenv("VALKYRIE_URL",  "http://localhost:8004")
SPYDER_URL    = os.getenv("SPYDER_URL",    "http://localhost:8005")
RAVEN_URL     = os.getenv("RAVEN_URL",     "http://localhost:8006")
DATAFLOW_URL  = os.getenv("DATAFLOW_URL",  "http://localhost:8007")


def get_heimdall_client() -> httpx.AsyncClient:
    global _heimdall
    if _heimdall is None:
        _heimdall = httpx.AsyncClient(
            base_url=HEIMDALL_URL, timeout=10.0, limits=_LIMITS
        )
    return _heimdall


def get_aria_client() -> httpx.AsyncClient:
    global _aria
    if _aria is None:
        _aria = httpx.AsyncClient(
            base_url=ARIA_URL, timeout=60.0, limits=_LIMITS
        )
    return _aria


def get_sage_client() -> httpx.AsyncClient:
    global _sage
    if _sage is None:
        _sage = httpx.AsyncClient(
            base_url=SAGE_URL, timeout=120.0, limits=_LIMITS
        )
    return _sage


def get_valkyrie_client() -> httpx.AsyncClient:
    global _valkyrie
    if _valkyrie is None:
        _valkyrie = httpx.AsyncClient(
            base_url=VALKYRIE_URL, timeout=120.0, limits=_LIMITS
        )
    return _valkyrie


def get_spyder_client() -> httpx.AsyncClient:
    global _spyder
    if _spyder is None:
        _spyder = httpx.AsyncClient(
            base_url=SPYDER_URL, timeout=180.0, limits=_LIMITS
        )
    return _spyder


def get_raven_client() -> httpx.AsyncClient:
    global _raven
    if _raven is None:
        _raven = httpx.AsyncClient(
            base_url=RAVEN_URL, timeout=120.0, limits=_LIMITS
        )
    return _raven


def get_dataflow_client() -> httpx.AsyncClient:
    global _dataflow
    if _dataflow is None:
        _dataflow = httpx.AsyncClient(
            base_url=DATAFLOW_URL, timeout=300.0, limits=_LIMITS
        )
    return _dataflow
