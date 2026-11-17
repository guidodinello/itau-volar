import io
import json
import urllib.error

import pytest

from itau_volar import cli
from itau_volar.db import Product, Source, connect, record_run
from itau_volar.http import Client

from .pages import gx_page


@pytest.fixture
def database(tmp_path, monkeypatch):
    path = tmp_path / "volar.db"
    monkeypatch.setenv("VOLAR_DB", str(path))
    connection = connect(path)
    record_run(
        connection,
        Source.TIENDA,
        "category:257",
        [
            Product(
                source=Source.TIENDA,
                id=1,
                name="Auriculares JBL Tune",
                currency="U$S",
                price=69.0,
                miles=2760,
                price_with_miles=35.0,
                url="https://example.test/1",
            ),
            Product(source=Source.TIENDA, id=2, name="Parlante JBL Go", currency="U$S", price=49.0),
        ],
    )
    connection.close()


def serve(monkeypatch, respond) -> None:
    """Replace the network: every GET is answered by `respond(url)`."""
    monkeypatch.setattr(Client, "get", lambda _self, url: respond(url))


def test_search_json_prints_the_matching_products_as_data(database, capsys):
    exit_code = cli.main(["search", "auriculares", "--json"])

    products = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert products[0]["in_stock"] is True  # a JSON boolean, not SQLite's 1
    assert products == [
        {
            "source": "tienda",
            "id": 1,
            "name": "Auriculares JBL Tune",
            "category": None,
            "currency": "U$S",
            "price": 69.0,
            "miles": 2760,
            "price_with_miles": 35.0,
            "in_stock": True,
            "badges": None,
            "url": "https://example.test/1",
        }
    ]


def test_search_matches_words_ignoring_accents_and_case(database, capsys):
    cli.main(["search", "AURICULÁRES", "jbl"])

    out = capsys.readouterr().out
    assert "Auriculares JBL Tune" in out
    assert "Parlante" not in out


def test_show_json_prints_the_product_detail_as_data(monkeypatch, capsys):
    page = gx_page(
        {
            "vPRODUCTUI": {
                "Info": {
                    "Id": 7,
                    "Name": "Auriculares",
                    "StandardPrice": "75",
                    "StandardPriceCurrencySymbol": "U$S",
                    "SellPointValue": "0.0125",
                }
            }
        }
    )
    serve(monkeypatch, lambda _url: page)

    exit_code = cli.main(["show", "7", "--json"])

    shown = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert (shown["id"], shown["price"], shown["mile_value"]) == (7, 75.0, 0.0125)


def test_a_challenge_page_exits_with_the_blocked_code(monkeypatch, caplog):
    serve(monkeypatch, lambda _url: "<title>Just a moment...</title>")

    assert cli.main(["show", "7"]) == 3
    assert "blocked" in caplog.text


@pytest.mark.parametrize("status", [403, 429])
def test_a_refusing_http_status_exits_with_the_blocked_code(monkeypatch, status):
    def refuse(url):
        raise urllib.error.HTTPError(url, status, "refused", None, io.BytesIO())

    serve(monkeypatch, refuse)

    assert cli.main(["show", "7"]) == 3


def test_a_changed_layout_exits_with_the_generic_error_code(monkeypatch, caplog):
    serve(monkeypatch, lambda _url: "<html>new design</html>")

    assert cli.main(["show", "7"]) == 1
    assert "layout probably changed" in caplog.text


def test_a_server_error_is_not_reported_as_blocked(monkeypatch):
    def fail(url):
        raise urllib.error.HTTPError(url, 500, "boom", None, io.BytesIO())

    serve(monkeypatch, fail)

    assert cli.main(["show", "7"]) == 1
