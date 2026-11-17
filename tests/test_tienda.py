import pytest

from itau_volar import tienda

from .pages import gx_page, raw_product, search_page


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("U$S 75", 75.0),
        ("U$S 1.299", 1299.0),
        ("$ 2.490,50", 2490.5),
        ("+39.800", 39800.0),
        ("", None),
        (None, None),
    ],
)
def test_parse_amount_reads_uruguayan_number_format(text, expected):
    assert tienda.parse_amount(text) == expected


def test_parse_search_returns_total_and_the_card_price_split():
    page = search_page([raw_product(1595883, "Auriculares JBL")], total=553)

    total, listings = tienda.parse_search(page)

    assert total == 553
    assert [
        (p.id, p.name, p.currency, p.price, p.card_miles, p.price_with_card_miles) for p in listings
    ] == [(1595883, "Auriculares JBL", "U$S", 75.0, 3000, 38.0)]


def test_parse_search_takes_the_product_link_from_the_page_without_tracking_params():
    link = '<a href="/auriculares-jbl.producto?1595883,,42&amp;campaign=search">x</a>'
    page = search_page([raw_product(1595883)], total=1, body=link)

    _, [listing] = tienda.parse_search(page)

    assert listing.url == "https://www.tiendavolar.com.uy/auriculares-jbl.producto?1595883"


def test_parse_search_falls_back_to_the_short_link_when_the_page_has_none():
    _, [listing] = tienda.parse_search(search_page([raw_product(7)], total=1))

    assert listing.url == "https://www.tiendavolar.com.uy/p.producto?7"


def test_parse_search_recovers_a_truncated_name_from_the_visible_card():
    card = (
        "<div class=\"card-product-container\" data-id='9'>"
        '<span class="card-product-name">Consola SONY PS5 con 2 Juegos (Astro Bot + GT)</span>'
        "</div>"
    )
    page = search_page(
        [raw_product(9, "Consola SONY PS5 con 2 Juegos (Astro Bot +...")], total=1, body=card
    )

    _, [listing] = tienda.parse_search(page)

    assert listing.name == "Consola SONY PS5 con 2 Juegos (Astro Bot + GT)"


def test_parse_search_collects_badge_captions():
    product = raw_product(
        1,
        MarketingBadges=[{"caption": "Envíos Gratis"}],
        PromoBadges=[{"caption": "17% OFF"}, {"caption": ""}],
    )

    _, [listing] = tienda.parse_search(search_page([product], total=1))

    assert listing.badges == ("Envíos Gratis", "17% OFF")


def test_a_store_page_without_page_state_is_reported_as_a_layout_change():
    with pytest.raises(tienda.ParseError, match="layout probably changed"):
        tienda.parse_search("<html><title>Tecnología - Tienda Volar</title></html>")


def test_a_challenge_page_is_reported_as_blocked_not_as_a_layout_change():
    with pytest.raises(tienda.BlockedError, match="block or challenge page"):
        tienda.parse_search("<html><title>Just a moment...</title></html>")


def test_iter_search_walks_pages_until_the_total_is_reached():
    pages = {
        tienda.search_url(category=257, page=0): search_page(
            [raw_product(1), raw_product(2)], total=3
        ),
        tienda.search_url(category=257, page=1): search_page([raw_product(3)], total=3),
    }

    listings = list(tienda.iter_search(pages.__getitem__, category=257))

    assert [p.id for p in listings] == [1, 2, 3]


def test_iter_search_stops_when_a_page_repeats_instead_of_looping_forever():
    same_page = search_page([raw_product(1)], total=99)

    listings = list(tienda.iter_search(lambda _url: same_page))

    assert [p.id for p in listings] == [1]


def detail_page() -> str:
    state = {
        "vPRODUCTUI": {
            "Info": {
                "Id": 1595883,
                "ProductCode": "595883",
                "Name": "Auriculares JBL Wave Buds 2",
                "Brand": "JBL",
                "ProductBarCode": "1200130015373",
                "SellPointValue": "0.0125",
                "StandardPrice": "75",
                "StandardPriceCurrencySymbol": "U$S",
                "ProductObs": "<div>Sonido <b>Pure Bass</b><br>IP54</div>",
                "Uri": "https://www.tiendavolar.com.uy/jbl.producto?1595883",
            },
            "QuickBuy": {"StockMax": "89"},
        },
        "W0032IDSLIDERWITHPOINTS_Maxpointsvalue": "6000",
        "W0233vPRODUCTATTRIBUTESSDT": [
            {"AtributeName": "Bluetooth        ", "ProductAtributeCustomValue": "Bluetooth 5.3"},
            {"AtributeName": "Potencia", "ProductAtributeCustomValue": ""},
        ],
        "W0233gxhash_vPRODUCTATTRIBUTESSDT": "not-json-signature",
    }
    breadcrumb = (
        '<div id="TXTBREADCRUMB"><a href="/home">Inicio</a> / '
        '<a href="/c/257">Tecnología</a> / <a href="/c/1">Auriculares</a></div>'
    )
    return gx_page(state, breadcrumb)


def test_parse_detail_reads_price_miles_stock_and_identity():
    detail = tienda.parse_detail(detail_page(), "fallback-url")

    assert (detail.id, detail.brand, detail.barcode) == (1595883, "JBL", "1200130015373")
    assert (detail.currency, detail.price) == ("U$S", 75.0)
    assert (detail.mile_value, detail.max_miles, detail.stock_max) == (0.0125, 6000, 89)
    assert detail.url == "https://www.tiendavolar.com.uy/jbl.producto?1595883"


def test_parse_detail_keeps_only_attributes_that_have_a_value():
    detail = tienda.parse_detail(detail_page(), "fallback-url")

    assert detail.attributes == {"Bluetooth": "Bluetooth 5.3"}


def test_parse_detail_gives_the_category_path_without_the_home_link():
    detail = tienda.parse_detail(detail_page(), "fallback-url")

    assert detail.category_path == ("Tecnología", "Auriculares")


def test_parse_detail_turns_the_html_description_into_plain_text():
    detail = tienda.parse_detail(detail_page(), "fallback-url")

    assert detail.description == "Sonido Pure Bass\nIP54"


def test_parse_detail_rejects_a_page_that_is_not_a_product():
    with pytest.raises(tienda.ParseError, match="no vPRODUCTUI"):
        tienda.parse_detail(gx_page({}), "url")
