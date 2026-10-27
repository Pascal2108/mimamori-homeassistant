"""Client for mimamori's read-only API (GET /api/v1/summary)."""
from __future__ import annotations

import asyncio
import json
from typing import Any

import aiohttp
from yarl import URL

from .const import API_PATH, API_VERSION, MAX_RESPONSE_BYTES, REQUEST_TIMEOUT


class MimamoriError(Exception):
    """Any problem talking to mimamori."""


class CannotConnect(MimamoriError):
    """mimamori could not be reached or answered with a server error."""


class InvalidAuth(MimamoriError):
    """The token is wrong or was revoked."""


class RateLimited(MimamoriError):
    """Too many wrong tokens from this address; mimamori locks it out for a few minutes."""


class Redirected(MimamoriError):
    """The address redirects elsewhere, e.g. from http:// to https://."""


class NotMimamori(MimamoriError):
    """The answer is not one of mimamori's API."""


def normalize_url(raw: str) -> str:
    """The base address of mimamori, e.g. https://mimamori.example.com, without a trailing
    slash. Raises ValueError for anything that is not an http(s) address."""
    url = URL(raw.strip())
    if url.scheme not in ("http", "https") or not url.host:
        raise ValueError("not an http(s) address")
    if url.user or url.password or url.query_string or url.fragment:
        raise ValueError("an address without user, query or fragment")
    return str(url.with_path(url.path.rstrip("/"))).rstrip("/")


class MimamoriClient:
    """Fetches the summary. The token is only ever sent to the configured address."""

    def __init__(self, session: aiohttp.ClientSession, url: str, token: str) -> None:
        self._session = session
        self._url = url + API_PATH
        self._headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    async def summary(self) -> dict[str, Any]:
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                # No redirects: they could lead to another host or to plain HTTP, and a
                # redirect from http:// to https:// means the user should enter https://
                async with self._session.get(self._url, headers=self._headers,
                                             allow_redirects=False) as resp:
                    if resp.status == 401:
                        raise InvalidAuth
                    if resp.status == 429:
                        raise RateLimited
                    if 300 <= resp.status < 400:
                        raise Redirected
                    if resp.status == 404:
                        raise NotMimamori("no API here (mimamori older than v0.3.5?)")
                    if resp.status != 200:
                        raise CannotConnect(f"HTTP {resp.status}")
                    body = await resp.content.read(MAX_RESPONSE_BYTES + 1)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise CannotConnect(str(err) or type(err).__name__) from err
        if len(body) > MAX_RESPONSE_BYTES:
            raise NotMimamori("answer too large")
        try:
            data = json.loads(body)
        except ValueError as err:
            raise NotMimamori("answer is not JSON") from err
        if not isinstance(data, dict) or data.get("api_version") != API_VERSION \
                or not isinstance(data.get("status"), dict):
            raise NotMimamori("unexpected answer")
        return data
