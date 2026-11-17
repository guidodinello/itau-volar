import json

from itau_volar import volar


def test_parse_catalog_maps_miles_category_stock_and_link():
    body = json.dumps(
        {
            "count": 2,
            "products": [
                {
                    "id": 6352048,
                    "name": " Divino - En Local - $1.000 ",
                    "miles": 2000,
                    "category": {"description": "Gastronomía"},
                    "isOutOfStock": False,
                    "isExternal": False,
                },
                {
                    "id": 7,
                    "name": "Agotado",
                    "miles": 500,
                    "category": None,
                    "isOutOfStock": True,
                    "isExternal": True,
                },
            ],
        }
    )

    first, second = volar.parse_catalog(body)

    assert first == volar.CatalogItem(
        id=6352048,
        name="Divino - En Local - $1.000",
        category="Gastronomía",
        miles=2000,
        in_stock=True,
        is_external=False,
        url="https://www.itauvolar.com.uy/volar/#/productos/6352048",
    )
    assert (second.category, second.in_stock, second.is_external) == (None, False, True)


def test_fetch_catalog_sends_only_the_fields_the_server_accepts():
    sent = []

    def post_json(url, body):
        sent.append((url, body))
        return json.dumps({"products": []})

    assert volar.fetch_catalog(post_json) == []
    expected_body = {"orderBy": "miles", "order": "asc", "channelName": "VOLAR"}
    assert sent == [(volar.SEARCH_URL, expected_body)]
