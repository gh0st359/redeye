"""Shared HTTP helpers for built-in tools."""
from __future__ import annotations

import httpx

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 RedEye/1.0"
)
API_UA = "RedEye/1.0 (osint-workbench; +https://github.com/redeye-osint/redeye)"


def client(timeout: float = 25.0, api: bool = False) -> httpx.Client:
    return httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": API_UA if api else UA, "Accept": "*/*"},
    )


def get_json(url: str, *, params: dict | None = None, headers: dict | None = None,
             timeout: float = 25.0) -> tuple[int, object]:
    with client(timeout=timeout, api=True) as c:
        r = c.get(url, params=params, headers=headers or {})
        return r.status_code, r.json()
