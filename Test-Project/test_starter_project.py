from types import SimpleNamespace
import pandas
import project.project_starter as app
from sqlalchemy import create_engine, inspect, text
# pyrefly: ignore [missing-import]
import pytest
from datetime import datetime

def test_generate_sample_inventory():
    inventory = app.generate_sample_inventory(app.paper_supplies, coverage=0.4, seed=137)
    assert len(inventory) == int(len(app.paper_supplies) * 0.4)
    assert inventory["item_name"].is_unique
    assert inventory["current_stock"].between(200, 799).all()
    assert inventory["min_stock_level"].between(50, 149).all()
    
    catalog = {item["item_name"]: item for item in app.paper_supplies}

    for row in inventory.itertuples():
        original = catalog[row.item_name]
        assert row.category == original["category"]
        assert row.unit_price == original["unit_price"]

def test_generate_sample_inventory_is_reproducible():
    first = app.generate_sample_inventory(app.paper_supplies, seed=137)
    second = app.generate_sample_inventory(app.paper_supplies, seed=137)
    pandas.testing.assert_frame_equal(first, second)

def test_init_database(tmp_path, monkeypatch):
    pandas.DataFrame([
        {"request": "Please quote A4 paper"}
    ]).to_csv(tmp_path / "quote_requests.csv", index=False)

    pandas.DataFrame([{
        "total_amount": 125.50,
        "quote_explanation": "Sample quote",
        "request_metadata": (
            "{'job_type': 'printing', 'order_size': 'bulk', "
            "'event_type': 'conference'}"
        ),
    }]).to_csv(tmp_path / "quotes.csv", index=False)

    monkeypatch.chdir(tmp_path)
    engine = create_engine("sqlite:///:memory:")


    try:
        assert app.init_database(engine, seed=137) is engine
        assert{
            "transactions",
            "quote_requests",
            "quotes",
            "inventory"
        }.issubset(inspect(engine).get_table_names())

        with engine.connect() as connection:
            inventory_count = connection.execute(
                text("SELECT COUNT(*) FROM inventory")
            ).scalar_one()
            stock_order_count = connection.execute(
                text(
                    "SELECT COUNT(*) FROM transactions "
                    "WHERE transaction_type = 'stock_orders'"
                )
            ).scalar_one()
            starting_cash = connection.execute(
                text(
                    "SELECT price FROM transactions "
                    "WHERE item_name IS NULL AND transaction_type = 'sales'"
                )
            ).scalar_one()
            quote = connection.execute(
                text(
                    "SELECT job_type, order_size, event_type "
                    "FROM quotes WHERE request_id = 1"
                )
            ).one()

            assert inventory_count == int(len(app.paper_supplies) * 0.4)
            assert stock_order_count == inventory_count
            assert starting_cash == 50_000.0
            assert quote == ('printing', 'bulk', 'conference')
    finally:
        engine.dispose()
    
        
@pytest.fixture
def transaction_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:")

    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_name TEXT,
                transaction_type TEXT,
                units INTEGER,
                price REAL,
                transaction_date TEXT
            )
        """))

    monkeypatch.setattr(app, "db_engine", engine)
    try:
        yield engine
    finally:
        engine.dispose()

@pytest.mark.parametrize(
    ("transaction_type", "date", "expected_date"),
    [
        ("sales", "2025-01-03", "2025-01-03"),
        ("stock_orders", datetime(2025, 1, 3, 14, 0), "2025-01-03T14:00:00"),
    ],
)
def test_create_transaction_saves_record(
    transaction_db, transaction_type, date, expected_date
):
    transaction_id = app.create_transaction(
        item_name="A4 paper",
        transaction_type=transaction_type,
        quantity=10,
        price=12.50,
        date=date,
    )

    with transaction_db.connect() as connection:
        row = connection.execute(
            text("SELECT * FROM transactions WHERE id = :id"),
            {"id": transaction_id},
        ).mappings().one()
    assert row["item_name"] == "A4 paper"
    assert row["transaction_type"] == transaction_type
    assert row["units"] == 10
    assert row["price"] == pytest.approx(12.50)
    assert row["transaction_date"] == expected_date

def test_create_transaction_rejects_invalid_type(transaction_db):
    with pytest.raises(ValueError, match="Transaction type must be"):
        app.create_transaction(
            item_name="A4 paper",
            transaction_type="refund",
            quantity=10,
            price=12.50,
            date="2025-01-03",
        )
    with transaction_db.connect() as connection:
        count = connection.execute(
            text("SELECT COUNT(*) FROM transactions")
        ).scalar_one()

    assert count == 0

    @pytest.mark.parametrize(
        ("as_of_date", "expected"),
        [
            ("2025-01-01", {"A4 paper": 100}),
            ("2025-01-02", {"A4 paper": 80, "Cardstock": 5}),
            ("2025-01-03", {"A4 paper": 80}),
            ("2025-01-04", {"Colored paper": 9}),
        ],
    )
    def test_get_all_inventory(transaction_db, as_of_date, expected):
        transactions = [
            ("A4 paper", "stock_orders", 100, "2025-01-01"),
            ("A4 paper", "sales", 20, "2025-01-02"),
            ("A4 paper", "sales", 80, "2025-01-04"),
            ("Cardstock", "stock_orders", 5, "2025-01-02"),
            ("Cardstock", "sales", 7, "2025-01-03"),
            ("Colored paper", "stock_orders", 9, "2025-01-04"),
            (None, "sales", None, "2025-01-01"),  # Cash-only record
        ]

        with transaction_db.begin() as connection:
            connection.execute(
                text("""
                    INSERT INTO transactions
                    (item_name, transaction_type, units, transaction_date)
                    VALUES
                    (:item_name, :transaction_type, :units, :transaction_date)
                """),
                [
                    {
                        "item_name": item_name,
                        "transaction_type": transaction_type,
                        "units": units,
                        "transaction_date": date,
                    }
                    for item_name, transaction_type, units, date in transactions
                ],
            )
            assert app.get_all_inventory(as_of_date) == expected

def test_get_all_inventory_when_empty(transaction_db):
    assert app.get_all_inventory("2025-01-03") == {}

@pytest.mark.parametrize(
    ("quantity","expected_date"),
    [
        (10, "2025-01-01"),  # same day
        (11, "2025-01-02"),
        (100, "2025-01-02"),
        (101, "2025-01-05"),
        (1000, "2025-01-05"),
        (1001, "2025-01-08")
    ],
)
def test_get_supplier_delivery_date_boundaries(quantity, expected_date):
    """
    Test that the supplier delivery date is calculated correctly based on quantity.

    Args:
        quantity (int): The quantity of paper to order.
        expected_date (str): The expected delivery date.
    """
    assert (
        app.get_supplier_delivery_date("2025-01-01", quantity) == expected_date
    )

def test_get_supplier_delivery_date_accepts_timestamp():
    """
    Test that the supplier delivery date accepts a timestamp as input.

    Args:
        None

    Returns:
        None
    """
    assert (
        app.get_supplier_delivery_date("2025-01-01T16:30:00", 11) == "2025-01-02"
    )


@pytest.mark.parametrize(
    ("as_of_date", "expected_balance"),
    [
        ("2024-12-31", 0.0),
        ("2025-01-01", 50_000.0),
        ("2025-01-02", 49_879.75),
        (datetime(2025, 1, 3), 49_950.0),
        ("2025-01-04", 50_050.0),
    ],
)


def test_get_cash_balance(transaction_db, as_of_date, expected_balance):
    with transaction_db.begin() as connection:
        connection.execute(
            text("""
                INSERT INTO transactions
                (item_name, transaction_type, units, price, transaction_date)
                VALUES
                (:item_name, :type, :units, :price, :date)
            """),
            [
                {
                    "item_name": None,
                    "type": "sales",
                    "units": None,
                    "price": 50_000.0,
                    "date": "2025-01-01",
                },
                {
                    "item_name": "A4 paper",
                    "type": "stock_orders",
                    "units": 100,
                    "price": 120.25,
                    "date": "2025-01-02",
                },
                {
                    "item_name": "A4 paper",
                    "type": "sales",
                    "units": 20,
                    "price": 70.25,
                    "date": "2025-01-03",
                },
                {
                    "item_name": "Cardstock",
                    "type": "sales",
                    "units": 10,
                    "price": 100.0,
                    "date": "2025-01-04",
                },
            ],
        )

    assert app.get_cash_balance(as_of_date) == pytest.approx(expected_balance) 

def test_generate_financial_report(transaction_db):
    pandas.DataFrame([
        {"item_name": "A4 paper", "unit_price": 2.0},
        {"item_name": "Cardstock", "unit_price": 4.0},
    ]).to_sql("inventory", transaction_db, index=False)

    with transaction_db.begin() as connection:
        connection.execute(
            text("""
                INSERT INTO transactions
                    (item_name, transaction_type, units, price, transaction_date)
                VALUES
                    (:item_name, :type, :units, :price, :date)
            """),
            [
                {"item_name": "A4 paper", "type": "stock_orders",
                 "units": 10, "price": 4.0, "date": "2025-01-01"},
                {"item_name": "Cardstock", "type": "stock_orders",
                 "units": 5, "price": 3.0, "date": "2025-01-01"},
                {"item_name": "A4 paper", "type": "sales",
                 "units": 3, "price": 9.0, "date": "2025-01-02"},
                {"item_name": "Cardstock", "type": "sales",
                 "units": 2, "price": 7.0, "date": "2025-01-02"},
                # Must not affect a report dated January 2.
                {"item_name": "A4 paper", "type": "sales",
                 "units": 1, "price": 3.0, "date": "2025-01-03"},
            ],
        )

    report = app.generate_financial_report("2025-01-02")

    # Cash: (9 + 7) - (4 + 3) = 9
    assert report["as_of_date"] == "2025-01-02"
    assert report["cash_balance"] == pytest.approx(9.0)

    # Inventory: (10 - 3) * 2 + (5 - 2) * 4 = 26
    assert report["inventory_value"] == pytest.approx(26.0)
    assert report["total_assets"] == pytest.approx(35.0)

    summary = {
        item["item_name"]: item for item in report["inventory_summary"]
    }
    assert summary["A4 paper"]["stock"] == 7
    assert summary["A4 paper"]["value"] == pytest.approx(14.0)
    assert summary["Cardstock"]["stock"] == 3
    assert summary["Cardstock"]["value"] == pytest.approx(12.0)

    top_products = report["top_selling_products"]
    assert [item["item_name"] for item in top_products] == [
        "A4 paper", "Cardstock"
    ]
    assert [item["total_units"] for item in top_products] == [3, 2]

@pytest.fixture
def quote_history_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    monkeypatch.setattr(app, "db_engine", engine)

    pandas.DataFrame([
        {"id": 1, "response": "A4 paper for posters"},
        {"id": 2, "response": "Cardstock invitations"},
        {"id": 3, "response": "Letter supplies"},
        {"id": 4, "response": "Envelopes"},
    ]).to_sql("quote_requests", engine, index=False)

    quotes = [
        (1, 20.0, "Standard stock", "2025-01-01"),
        (2, 30.0, "Premium finish", "2025-01-03"),
        (3, 40.0, "A4 bulk pricing", "2025-01-04"),
        (4, 10.0, "Budget option", "2025-01-02"),
    ]
    pandas.DataFrame([
        {
            "request_id": request_id,
            "total_amount": amount,
            "quote_explanation": explanation,
            "job_type": "printing",
            "order_size": "small",
            "event_type": "meeting",
            "order_date": date,
        }
        for request_id, amount, explanation, date in quotes
    ]).to_sql("quotes", engine, index=False)

    try:
        yield engine
    finally:
        engine.dispose()


def test_search_quote_history_matches_request_and_explanation(quote_history_db):
    results = app.search_quote_history(["a4"])

    # The newest match comes first. "A4" occurs in a quote explanation
    # for the first result and in the customer request for the second.
    assert [row["original_request"] for row in results] == [
        "Letter supplies",
        "A4 paper for posters",
    ]
    assert results[0]["total_amount"] == pytest.approx(40.0)
    assert results[0]["job_type"] == "printing"


def test_search_quote_history_respects_limit(quote_history_db):
    results = app.search_quote_history([], limit=2)

    assert [row["original_request"] for row in results] == [
        "Letter supplies",
        "Cardstock invitations",
    ]


def test_search_quote_history_no_match(quote_history_db):
    assert app.search_quote_history(["nonexistent"]) == []


from pathlib import Path
from unittest.mock import Mock


def test_build_model_uses_environment(monkeypatch):
    load_mock = Mock()
    provider = object()
    model = object()
    provider_mock = Mock(return_value=provider)
    model_mock = Mock(return_value=model)

    monkeypatch.setattr(app, "load_dotenv", load_mock)
    monkeypatch.setattr(app, "OpenAIProvider", provider_mock)
    monkeypatch.setattr(app, "OpenAIChatModel", model_mock)
    monkeypatch.setenv("UDACITY_OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("MODEL_NAME", "test-model")

    assert app.build_model() is model
    load_mock.assert_called_once_with(
        Path(app.__file__).resolve().parents[1] / ".env"
    )
    provider_mock.assert_called_once_with(
        api_key="test-key",
        base_url="https://example.invalid/v1",
    )
    model_mock.assert_called_once_with("test-model", provider=provider)


@pytest.mark.parametrize(
    "missing_name",
    ["UDACITY_OPENAI_API_KEY", "OPENAI_BASE_URL", "MODEL_NAME"],
)
def test_build_model_rejects_missing_configuration(monkeypatch, missing_name):
    monkeypatch.setattr(app, "load_dotenv", lambda *_args: None)
    monkeypatch.setenv("UDACITY_OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("MODEL_NAME", "test-model")
    monkeypatch.delenv(missing_name)

    with pytest.raises(RuntimeError, match=missing_name):
        app.build_model()

def test_orchestrator_routes_new_order_to_quote(monkeypatch):
    message = "Quote 100 sheets of A4 paper"
    model = object()

    router = Mock()
    router.run_sync.return_value = SimpleNamespace(
        output=app.RouteDecision(intent="quote")
    )
    quotation = Mock(return_value='{"status": "ready"}')
    sale = Mock()

    monkeypatch.setattr(app, "answer_quote_request", quotation)
    monkeypatch.setattr(app, "finalize_sale", sale)

    response = app.handle_customer_request(
        message,
        "2025-04-01",
        request_id="req-1",
        model=model,
        orchestrator=router,
    )

    assert response == '{"status": "ready"}'
    quotation.assert_called_once_with(
        message,
        "2025-04-01",
        request_id="req-1",
        model=model,
    )
    sale.assert_not_called()