from datetime import UTC, datetime

import pytest

from itau_volar.db import CHANGES_SQL, Product, Source, connect, fold, last_two_runs, record_run


@pytest.fixture
def connection(tmp_path):
    connection = connect(tmp_path / "volar.db")
    yield connection
    connection.close()


def tienda_product(pid: int, price: float, *, in_stock: bool = True) -> Product:
    return Product(
        source=Source.TIENDA, id=pid, name=f"producto {pid}", price=price, in_stock=in_stock
    )


def changes(connection, source=Source.TIENDA) -> set[tuple]:
    previous, newest = last_two_runs(connection, source)
    rows = connection.execute(
        CHANGES_SQL, {"old": previous["run_id"], "new": newest["run_id"], "source": source}
    )
    return {(row["change"], row["id"], row["before"], row["after"]) for row in rows}


def test_fold_ignores_case_and_accents():
    assert fold("Tecnología") == fold("TECNOLOGIA") == "tecnologia"


def test_changes_report_every_kind_of_difference_between_two_syncs(connection):
    record_run(
        connection,
        Source.TIENDA,
        "category:257",
        [
            tienda_product(1, 100),
            tienda_product(2, 100),
            tienda_product(3, 100),
            tienda_product(4, 100),
            tienda_product(5, 100, in_stock=False),
            tienda_product(6, 100),
            tienda_product(7, 100),
        ],
    )
    record_run(
        connection,
        Source.TIENDA,
        "category:257",
        [
            tienda_product(1, 100),
            tienda_product(2, 80),
            tienda_product(3, 120),
            tienda_product(5, 100),
            tienda_product(6, 100, in_stock=False),
            tienda_product(8, 50),
        ],
    )

    assert changes(connection) == {
        ("cheaper", 2, 100, 80),
        ("pricier", 3, 100, 120),
        ("gone", 4, 100, None),
        ("restocked", 5, 100, 100),
        ("out of stock", 6, 100, 100),
        ("gone", 7, 100, None),
        ("new", 8, None, 50),
    }


def test_changes_compare_miles_for_products_without_a_cash_price(connection):
    voucher = Product(source=Source.VOLAR, id=1, name="voucher", miles=2000)
    cheaper = Product(source=Source.VOLAR, id=1, name="voucher", miles=1500)
    record_run(connection, Source.VOLAR, "catalog", [voucher])
    record_run(connection, Source.VOLAR, "catalog", [cheaper])

    assert changes(connection, Source.VOLAR) == {("cheaper", 1, 2000, 1500)}


def test_runs_with_a_different_scope_are_not_compared(connection):
    record_run(connection, Source.TIENDA, "category:257", [tienda_product(1, 100)])
    record_run(connection, Source.TIENDA, "category:0", [tienda_product(1, 100)])

    assert last_two_runs(connection, Source.TIENDA) is None


def test_runs_of_another_source_are_not_compared(connection):
    record_run(connection, Source.TIENDA, "category:257", [tienda_product(1, 100)])
    record_run(connection, Source.VOLAR, "catalog", [])
    record_run(connection, Source.TIENDA, "category:257", [tienda_product(1, 90)])

    assert changes(connection) == {("cheaper", 1, 100, 90)}


def test_a_resync_keeps_first_seen_and_updates_the_current_price(connection):
    monday, tuesday = datetime(2026, 11, 16, tzinfo=UTC), datetime(2026, 11, 17, tzinfo=UTC)
    record_run(connection, Source.TIENDA, "category:257", [tienda_product(1, 100)], at=monday)
    record_run(connection, Source.TIENDA, "category:257", [tienda_product(1, 90)], at=tuesday)

    row = connection.execute(
        "SELECT first_seen, last_seen, price, COUNT(*) AS n FROM products"
    ).fetchone()

    assert tuple(row) == ("2026-11-16T00:00:00+00:00", "2026-11-17T00:00:00+00:00", 90, 1)
