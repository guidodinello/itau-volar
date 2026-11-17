"""Builders for minimal Tienda Volar pages: only the parts the parsers read."""

import html
import json
from typing import Any


def gx_page(state: dict[str, Any], body: str = "") -> str:
    encoded = html.escape(json.dumps(state), quote=True)
    state_input = f'<input type="hidden" name="GXState" value=\'{encoded}\' />'
    return f"<html><body>{body}{state_input}</body></html>"


def raw_product(pid: int, name: str = "Producto", **overrides: Any) -> dict[str, Any]:
    return {
        "Id": pid,
        "Code": str(pid)[1:],
        "Name": name,
        "Points": "+3.000",
        "Price": "U$S 75",
        "PriceAndPoints": "U$S 38",
        "CurrencySymbol": "U$S",
        "MarketingBadges": [],
        "PromoBadges": [],
    } | overrides


def search_page(products: list[dict[str, Any]], total: int, body: str = "") -> str:
    return gx_page({"vSEARCHRESPONSE": {"TotalCount": total, "Product": products}}, body)
