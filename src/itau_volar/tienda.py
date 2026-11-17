"""Tienda Volar (tiendavolar.com.uy): physical products paid with cash and/or miles.

The site is server-rendered (GeneXus). Every page carries its state as JSON in a
hidden `GXState` input, so we read that instead of scraping the visible HTML.
"""

from __future__ import annotations

import html
import json
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

BASE = "https://www.tiendavolar.com.uy"
TECNOLOGIA = 257
ALL_CATEGORIES = 0

_GXSTATE = re.compile(r"name=\"GXState\" value='(.*?)'\s*/?>", re.S)
_PRODUCT_LINK = re.compile(r'href="(/[^"?]*\.producto\?(\d+))')
_TRUNCATION_MARK = "..."


# Text that only appears in a block or challenge page, never in a store page.
_BLOCK_PAGE_MARKERS = (
    "Just a moment",
    "cf-browser-verification",
    "Attention Required",
    "Access Denied",
    "Request unsuccessful",
)


class TiendaError(RuntimeError):
    """Base for every error this module raises."""


class ParseError(TiendaError):
    """The store answered, but not with the structure this module reads."""


class BlockedError(TiendaError):
    """The request was answered by a block or challenge page, not by the store."""


@dataclass(frozen=True, slots=True)
class Listing:
    """One product as it appears in a search/category page.

    `card_miles` and `price_with_card_miles` are the split the card advertises
    ("U$S 38 + 3.000 millas"), not the maximum miles the product accepts.
    """

    id: int
    code: str
    name: str
    url: str
    currency: str
    price: float | None
    card_miles: int | None
    price_with_card_miles: float | None
    badges: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Detail:
    """One product as it appears on its own page."""

    id: int
    code: str
    name: str
    brand: str | None
    barcode: str | None
    currency: str
    price: float | None
    mile_value: float | None
    max_miles: int | None
    stock_max: int | None
    category_path: tuple[str, ...]
    description: str
    attributes: dict[str, str]
    url: str


def parse_gxstate(page: str) -> dict[str, Any]:
    match = _GXSTATE.search(page)
    if not match:
        if any(marker in page for marker in _BLOCK_PAGE_MARKERS):
            raise BlockedError("got a block or challenge page instead of the store page")
        raise ParseError("page has no GXState block; the site layout probably changed")
    return json.loads(html.unescape(match.group(1)))


def parse_amount(text: object) -> float | None:
    """'U$S 1.299' -> 1299.0, '$ 2.490,50' -> 2490.5, '+3.000' -> 3000.0."""
    if text is None:
        return None
    digits = re.sub(r"[^\d.,]", "", str(text).replace("U$S", ""))
    if not digits:
        return None
    return float(digits.replace(".", "").replace(",", "."))


def search_url(*, text: str = "", category: int = ALL_CATEGORIES, page: int = 0) -> str:
    query = quote(text) if text else "*%3A*"
    return f"{BASE}/busqueda?0,0,{query},{category},0,0,,,false,,,,{page}"


def product_url(product_id: int) -> str:
    return f"{BASE}/p.producto?{product_id}"


def parse_search(page: str) -> tuple[int, list[Listing]]:
    """Return (total result count, products on this page)."""
    response = _as_obj(parse_gxstate(page).get("vSEARCHRESPONSE"))
    if not response:
        raise ParseError("page has no vSEARCHRESPONSE")
    urls = {int(pid): BASE + href for href, pid in _PRODUCT_LINK.findall(page)}

    listings = []
    for raw in response.get("Product", []):
        pid = int(raw["Id"])
        name = raw["Name"]
        if name.endswith(_TRUNCATION_MARK):
            name = _name_from_card(page, pid) or name
        badges = raw.get("MarketingBadges", []) + raw.get("PromoBadges", [])
        listings.append(
            Listing(
                id=pid,
                code=str(raw.get("Code", "")),
                name=name,
                url=urls.get(pid, product_url(pid)),
                currency=raw.get("CurrencySymbol", ""),
                price=parse_amount(raw.get("Price")),
                card_miles=_to_int(parse_amount(raw.get("Points"))),
                price_with_card_miles=parse_amount(raw.get("PriceAndPoints")),
                badges=tuple(b["caption"] for b in badges if b.get("caption")),
            )
        )
    return int(response.get("TotalCount", len(listings))), listings


def iter_search(
    fetch: Callable[[str], str],
    *,
    text: str = "",
    category: int = ALL_CATEGORIES,
    on_page: Callable[[int, int], None] | None = None,
) -> Iterator[Listing]:
    """Walk every result page. `fetch` maps a URL to its body.

    `on_page(products_so_far, total)` is called after each page.
    """
    seen: set[int] = set()
    page = 0
    while True:
        total, listings = parse_search(fetch(search_url(text=text, category=category, page=page)))
        fresh = [item for item in listings if item.id not in seen]
        if not fresh:
            return
        seen.update(item.id for item in fresh)
        yield from fresh
        if on_page:
            on_page(len(seen), total)
        if len(seen) >= total:
            return
        page += 1


def parse_detail(page: str, url: str) -> Detail:
    state = parse_gxstate(page)
    ui = _as_obj(state.get("vPRODUCTUI"))
    if not ui:
        raise ParseError("page has no vPRODUCTUI (product missing or layout changed)")
    info = ui["Info"]
    attributes = _attributes(state)
    stock = (ui.get("QuickBuy") or {}).get("StockMax")
    return Detail(
        id=int(info["Id"]),
        code=str(info.get("ProductCode", "")),
        name=info["Name"],
        brand=info.get("Brand") or attributes.get("Marca"),
        barcode=info.get("ProductBarCode") or None,
        currency=info.get("StandardPriceCurrencySymbol", ""),
        price=parse_amount(info.get("StandardPrice")),
        mile_value=float(info["SellPointValue"]) if info.get("SellPointValue") else None,
        max_miles=_max_miles(state),
        stock_max=int(stock) if stock not in (None, "") else None,
        category_path=_breadcrumb(page),
        description=_strip_tags(info.get("ProductObs", "")),
        attributes=attributes,
        url=info.get("Uri") or url,
    )


def _as_obj(value: Any) -> Any:
    """GXState stores nested objects either inline or as a JSON string."""
    return json.loads(value) if isinstance(value, str) else value


def _to_int(value: float | None) -> int | None:
    return None if value is None else round(value)


def _name_from_card(page: str, pid: int) -> str | None:
    """The JSON truncates long names; the visible card keeps the full one."""
    match = re.search(
        rf"data-id='{pid}'.*?<span class=\"card-product-name\">(.*?)</span>", page, re.S
    )
    return html.unescape(match.group(1)).strip() if match else None


def _attributes(state: dict[str, Any]) -> dict[str, str]:
    attributes: dict[str, str] = {}
    for key, value in state.items():
        if not key.endswith("vPRODUCTATTRIBUTESSDT") or "gxhash" in key:
            continue
        for attr in _as_obj(value) or []:
            name = attr.get("AtributeName", "").strip()
            custom_value = str(attr.get("ProductAtributeCustomValue", "")).strip()
            if name and custom_value:
                attributes[name] = custom_value
    return attributes


def _max_miles(state: dict[str, Any]) -> int | None:
    for key, value in state.items():
        if key.endswith("IDSLIDERWITHPOINTS_Maxpointsvalue"):
            return _to_int(parse_amount(value))
    return None


def _breadcrumb(page: str) -> tuple[str, ...]:
    match = re.search(r'id="[^"]*BREADCRUMB[^"]*"[^>]*>(.*?)</div>', page, re.S | re.I)
    if not match:
        return ()
    links = re.findall(r"<a[^>]*>(.*?)</a>", match.group(1), re.S)
    names = (html.unescape(re.sub(r"<[^>]+>", "", link)).strip() for link in links)
    return tuple(name for name in names if name and name.lower() != "inicio")


def _strip_tags(text: str) -> str:
    text = re.sub(r"<br\s*/?>|</p>|</div>|</li>", "\n", text, flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    return re.sub(r"\n{3,}", "\n\n", text).strip()
