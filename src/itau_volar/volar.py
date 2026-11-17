"""Itaú Volar catalog (itauvolar.com.uy): vouchers and experiences paid in miles.

The web app talks to a JSON API that answers without login.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass

BASE = "https://www.itauvolar.com.uy/volar"
SEARCH_URL = f"{BASE}/api/catalog/search"

# The payload the web app itself sends; unknown fields make the server return 500.
_FULL_CATALOG_QUERY = {"orderBy": "miles", "order": "asc", "channelName": "VOLAR"}


@dataclass(frozen=True, slots=True)
class CatalogItem:
    id: int
    name: str
    category: str | None
    miles: int | None
    in_stock: bool
    is_external: bool
    url: str


def parse_catalog(body: str) -> list[CatalogItem]:
    return [
        CatalogItem(
            id=int(raw["id"]),
            name=raw["name"].strip(),
            category=(raw.get("category") or {}).get("description"),
            miles=raw.get("miles"),
            in_stock=not raw.get("isOutOfStock", False),
            is_external=bool(raw.get("isExternal")),
            url=f"{BASE}/#/productos/{raw['id']}",
        )
        for raw in json.loads(body)["products"]
    ]


def fetch_catalog(post_json: Callable[[str, dict[str, object]], str]) -> list[CatalogItem]:
    """Download the whole catalog in one request (about 15 seconds)."""
    return parse_catalog(post_json(SEARCH_URL, dict(_FULL_CATALOG_QUERY)))
