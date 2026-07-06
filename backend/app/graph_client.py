"""Small read-only Microsoft Graph client helpers.

The helpers in this module only issue HTTP GET requests. They are intentionally
minimal so provider modules can share Microsoft Graph transport behavior without
mixing endpoint-specific OneNote logic into the auth layer.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.graph_auth import get_development_access_token

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"


class MissingGraphTokenError(RuntimeError):
    """Raised when a read-only Graph request is made before login."""


class GraphRequestError(RuntimeError):
    """Raised when Microsoft Graph returns an error response."""


def _build_graph_url(path_or_url: str, query_params: dict[str, str] | None = None) -> str:
    """Build a Microsoft Graph URL from a relative path or absolute nextLink."""

    if path_or_url.startswith("https://"):
        url = path_or_url
    else:
        normalized_path = path_or_url if path_or_url.startswith("/") else f"/{path_or_url}"
        url = f"{GRAPH_BASE_URL}{normalized_path}"

    if query_params:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}{urlencode(query_params)}"

    return url


def _format_graph_http_error(exc: HTTPError, error_body: str) -> str:
    """Return a readable Graph error without hiding tenant or consent details."""

    try:
        payload = json.loads(error_body)
    except json.JSONDecodeError:
        payload = {}

    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        code = error.get("code")
        message = error.get("message")
        if code or message:
            return f"Microsoft Graph returned HTTP {exc.code}: {code or 'error'} - {message or error_body}"

    return f"Microsoft Graph returned HTTP {exc.code}: {error_body}"


def graph_get_text(
    path_or_url: str,
    query_params: dict[str, str] | None = None,
    accept: str = "text/html",
) -> str:
    """Perform an authenticated read-only Microsoft Graph GET and return text."""

    access_token = get_development_access_token()
    if access_token is None:
        raise MissingGraphTokenError(
            "Microsoft Graph is not connected. Visit /auth/login first, then retry. "
            "If UCSD blocks consent, the ResearchOS app needs tenant approval."
        )

    request = Request(
        url=_build_graph_url(path_or_url=path_or_url, query_params=query_params),
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": accept,
        },
        method="GET",
    )

    try:
        with urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise GraphRequestError(_format_graph_http_error(exc, error_body)) from exc
    except URLError as exc:
        raise GraphRequestError(f"Microsoft Graph request failed: {exc.reason}") from exc


def graph_get(path_or_url: str, query_params: dict[str, str] | None = None) -> dict[str, Any]:
    """Perform an authenticated read-only Microsoft Graph GET request.

    The access token comes from the temporary development auth cache. Missing or
    expired tokens are converted into a clear local exception so API routes can
    return a helpful login message.
    """

    access_token = get_development_access_token()
    if access_token is None:
        raise MissingGraphTokenError(
            "Microsoft Graph is not connected. Visit /auth/login first, then retry."
        )

    request = Request(
        url=_build_graph_url(path_or_url=path_or_url, query_params=query_params),
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        },
        method="GET",
    )

    try:
        with urlopen(request, timeout=30) as response:
            raw_body = response.read().decode("utf-8")
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise GraphRequestError(_format_graph_http_error(exc, error_body)) from exc
    except URLError as exc:
        raise GraphRequestError(f"Microsoft Graph request failed: {exc.reason}") from exc

    if not raw_body:
        return {}

    parsed_body = json.loads(raw_body)
    if not isinstance(parsed_body, dict):
        raise GraphRequestError("Microsoft Graph returned an unexpected non-object response.")

    return parsed_body


def graph_get_all_pages(
    path: str,
    query_params: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Read a Microsoft Graph collection and follow ``@odata.nextLink`` pages."""

    items: list[dict[str, Any]] = []
    response = graph_get(path_or_url=path, query_params=query_params)

    while True:
        raw_values = response.get("value", [])
        if not isinstance(raw_values, list):
            raise GraphRequestError("Microsoft Graph collection response did not contain a list.")

        items.extend(item for item in raw_values if isinstance(item, dict))

        next_link = response.get("@odata.nextLink")
        if not isinstance(next_link, str) or not next_link:
            break

        response = graph_get(path_or_url=next_link)

    return items
