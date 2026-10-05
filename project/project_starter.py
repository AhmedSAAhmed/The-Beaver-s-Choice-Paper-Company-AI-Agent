import ast
import json
import os
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Dict, List, Literal, Union
from uuid import uuid4

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from sqlalchemy import create_engine, Engine, inspect, text

try:
    from .customer_responses import (
        customer_fulfillment_response,
        customer_message,
        customer_quote_response,
    )
except ImportError:  # Support running this file directly as a script.
    from customer_responses import (
        customer_fulfillment_response,
        customer_message,
        customer_quote_response,
    )

# Create an SQLite database
db_engine = create_engine("sqlite:///munder_difflin.db")

# List containing the different kinds of papers 
paper_supplies = [
    # Paper Types (priced per sheet unless specified)
    {"item_name": "A4 paper",                         "category": "paper",        "unit_price": 0.05},
    {"item_name": "Letter-sized paper",              "category": "paper",        "unit_price": 0.06},
    {"item_name": "Cardstock",                        "category": "paper",        "unit_price": 0.15},
    {"item_name": "Colored paper",                    "category": "paper",        "unit_price": 0.10},
    {"item_name": "Glossy paper",                     "category": "paper",        "unit_price": 0.20},
    {"item_name": "Matte paper",                      "category": "paper",        "unit_price": 0.18},
    {"item_name": "Recycled paper",                   "category": "paper",        "unit_price": 0.08},
    {"item_name": "Eco-friendly paper",               "category": "paper",        "unit_price": 0.12},
    {"item_name": "Poster paper",                     "category": "paper",        "unit_price": 0.25},
    {"item_name": "Banner paper",                     "category": "paper",        "unit_price": 0.30},
    {"item_name": "Kraft paper",                      "category": "paper",        "unit_price": 0.10},
    {"item_name": "Construction paper",               "category": "paper",        "unit_price": 0.07},
    {"item_name": "Wrapping paper",                   "category": "paper",        "unit_price": 0.15},
    {"item_name": "Glitter paper",                    "category": "paper",        "unit_price": 0.22},
    {"item_name": "Decorative paper",                 "category": "paper",        "unit_price": 0.18},
    {"item_name": "Letterhead paper",                 "category": "paper",        "unit_price": 0.12},
    {"item_name": "Legal-size paper",                 "category": "paper",        "unit_price": 0.08},
    {"item_name": "Crepe paper",                      "category": "paper",        "unit_price": 0.05},
    {"item_name": "Photo paper",                      "category": "paper",        "unit_price": 0.25},
    {"item_name": "Uncoated paper",                   "category": "paper",        "unit_price": 0.06},
    {"item_name": "Butcher paper",                    "category": "paper",        "unit_price": 0.10},
    {"item_name": "Heavyweight paper",                "category": "paper",        "unit_price": 0.20},
    {"item_name": "Standard copy paper",              "category": "paper",        "unit_price": 0.04},
    {"item_name": "Bright-colored paper",             "category": "paper",        "unit_price": 0.12},
    {"item_name": "Patterned paper",                  "category": "paper",        "unit_price": 0.15},

    # Product Types (priced per unit)
    {"item_name": "Paper plates",                     "category": "product",      "unit_price": 0.10},  # per plate
    {"item_name": "Paper cups",                       "category": "product",      "unit_price": 0.08},  # per cup
    {"item_name": "Paper napkins",                    "category": "product",      "unit_price": 0.02},  # per napkin
    {"item_name": "Disposable cups",                  "category": "product",      "unit_price": 0.10},  # per cup
    {"item_name": "Table covers",                     "category": "product",      "unit_price": 1.50},  # per cover
    {"item_name": "Envelopes",                        "category": "product",      "unit_price": 0.05},  # per envelope
    {"item_name": "Sticky notes",                     "category": "product",      "unit_price": 0.03},  # per sheet
    {"item_name": "Notepads",                         "category": "product",      "unit_price": 2.00},  # per pad
    {"item_name": "Invitation cards",                 "category": "product",      "unit_price": 0.50},  # per card
    {"item_name": "Flyers",                           "category": "product",      "unit_price": 0.15},  # per flyer
    {"item_name": "Party streamers",                  "category": "product",      "unit_price": 0.05},  # per roll
    {"item_name": "Decorative adhesive tape (washi tape)", "category": "product", "unit_price": 0.20},  # per roll
    {"item_name": "Paper party bags",                 "category": "product",      "unit_price": 0.25},  # per bag
    {"item_name": "Name tags with lanyards",          "category": "product",      "unit_price": 0.75},  # per tag
    {"item_name": "Presentation folders",             "category": "product",      "unit_price": 0.50},  # per folder

    # Large-format items (priced per unit)
    {"item_name": "Large poster paper (24x36 inches)", "category": "large_format", "unit_price": 1.00},
    {"item_name": "Rolls of banner paper (36-inch width)", "category": "large_format", "unit_price": 2.50},

    # Specialty papers
    {"item_name": "100 lb cover stock",               "category": "specialty",    "unit_price": 0.50},
    {"item_name": "80 lb text paper",                 "category": "specialty",    "unit_price": 0.40},
    {"item_name": "250 gsm cardstock",                "category": "specialty",    "unit_price": 0.30},
    {"item_name": "220 gsm poster paper",             "category": "specialty",    "unit_price": 0.35},
]

# Given below are some utility functions you can use to implement your multi-agent system

def generate_sample_inventory(paper_supplies: list, coverage: float = 0.4, seed: int = 137) -> pd.DataFrame:
    """
    Generate inventory for exactly a specified percentage of items from the full paper supply list.

    This function randomly selects exactly `coverage` × N items from the `paper_supplies` list,
    and assigns each selected item:
    - a random stock quantity between 200 and 800,
    - a minimum stock level between 50 and 150.

    The random seed ensures reproducibility of selection and stock levels.

    Args:
        paper_supplies (list): A list of dictionaries, each representing a paper item with
                               keys 'item_name', 'category', and 'unit_price'.
        coverage (float, optional): Fraction of items to include in the inventory (default is 0.4, or 40%).
        seed (int, optional): Random seed for reproducibility (default is 137).

    Returns:
        pd.DataFrame: A DataFrame with the selected items and assigned inventory values, including:
                      - item_name
                      - category
                      - unit_price
                      - current_stock
                      - min_stock_level
    """
    # Ensure reproducible random output
    np.random.seed(seed)

    # Calculate number of items to include based on coverage
    num_items = int(len(paper_supplies) * coverage)

    # Randomly select item indices without replacement
    selected_indices = np.random.choice(
        range(len(paper_supplies)),
        size=num_items,
        replace=False
    )

    # Extract selected items from paper_supplies list
    selected_items = [paper_supplies[i] for i in selected_indices]

    # Construct inventory records
    inventory = []
    for item in selected_items:
        inventory.append({
            "item_name": item["item_name"],
            "category": item["category"],
            "unit_price": item["unit_price"],
            "current_stock": np.random.randint(200, 800),  # Realistic stock range
            "min_stock_level": np.random.randint(50, 150)  # Reasonable threshold for reordering
        })

    # Return inventory as a pandas DataFrame
    return pd.DataFrame(inventory)

def _transaction_cutoff(as_of_date: Union[str, datetime]) -> tuple[str, str]:
    """Include an entire date, or stop at the precise time of a datetime."""
    if isinstance(as_of_date, datetime):
        return "<=", as_of_date.isoformat()
    next_day = datetime.strptime(as_of_date, "%Y-%m-%d") + timedelta(days=1)
    return "<", next_day.strftime("%Y-%m-%d")

def init_database(db_engine: Engine, seed: int = 137) -> Engine:
    """
    Set up the Munder Difflin database with all required tables and initial records.

    This function performs the following tasks:
    - Creates the 'transactions' table for logging stock orders and sales
    - Loads customer inquiries from 'quote_requests.csv' into a 'quote_requests' table
    - Loads previous quotes from 'quotes.csv' into a 'quotes' table, extracting useful metadata
    - Generates a random subset of paper inventory using `generate_sample_inventory`
    - Inserts initial financial records including available cash and starting stock levels

    Args:
        db_engine (Engine): A SQLAlchemy engine connected to the SQLite database.
        seed (int, optional): A random seed used to control reproducibility of inventory stock levels.
                              Default is 137.

    Returns:
        Engine: The same SQLAlchemy engine, after initializing all necessary tables and records.

    Raises:
        Exception: If an error occurs during setup, the exception is printed and raised.
    """
    try:
        base_tables = {"transactions", "inventory", "quotes", "quote_requests"}
        existing_tables = set(inspect(db_engine).get_table_names())
        if base_tables.issubset(existing_tables):
            return db_engine
        if base_tables.intersection(existing_tables):
            raise RuntimeError("Database initialization is incomplete; existing tables were preserved")

        # ----------------------------
        # 1. Create an empty 'transactions' table schema
        # ----------------------------
        transactions_schema = pd.DataFrame({
            "id": [],
            "item_name": [],
            "transaction_type": [],  # 'stock_orders' or 'sales'
            "units": [],             # Quantity involved
            "price": [],             # Total price for the transaction
            "transaction_date": [],  # ISO-formatted date
        })
        transactions_schema.to_sql("transactions", db_engine, if_exists="replace", index=False)

        # Set a consistent starting date
        initial_date = datetime(2025, 1, 1).isoformat()

        # ----------------------------
        # 2. Load and initialize 'quote_requests' table
        # ----------------------------
        quote_requests_path = Path("quote_requests.csv")
        if not quote_requests_path.is_file():
            quote_requests_path = Path(__file__).with_name("quote_requests.csv")
        quote_requests_df = pd.read_csv(quote_requests_path)
        quote_requests_df["id"] = range(1, len(quote_requests_df) + 1)
        quote_requests_df.to_sql("quote_requests", db_engine, if_exists="replace", index=False)

        # ----------------------------
        # 3. Load and transform 'quotes' table
        # ----------------------------
        quotes_path = Path("quotes.csv")
        if not quotes_path.is_file():
            quotes_path = Path(__file__).with_name("quotes.csv")
        quotes_df = pd.read_csv(quotes_path)
        quotes_df["request_id"] = range(1, len(quotes_df) + 1)
        quotes_df["order_date"] = initial_date

        # Unpack metadata fields (job_type, order_size, event_type) if present
        if "request_metadata" in quotes_df.columns:
            quotes_df["request_metadata"] = quotes_df["request_metadata"].apply(
                lambda x: ast.literal_eval(x) if isinstance(x, str) else x
            )
            quotes_df["job_type"] = quotes_df["request_metadata"].apply(lambda x: x.get("job_type", ""))
            quotes_df["order_size"] = quotes_df["request_metadata"].apply(lambda x: x.get("order_size", ""))
            quotes_df["event_type"] = quotes_df["request_metadata"].apply(lambda x: x.get("event_type", ""))

        # Retain only relevant columns
        quotes_df = quotes_df[[
            "request_id",
            "total_amount",
            "quote_explanation",
            "order_date",
            "job_type",
            "order_size",
            "event_type"
        ]]
        quotes_df.to_sql("quotes", db_engine, if_exists="replace", index=False)

        # ----------------------------
        # 4. Generate inventory and seed stock
        # ----------------------------
        inventory_df = generate_sample_inventory(paper_supplies, seed=seed)

        # Seed initial transactions
        initial_transactions = []

        # Add a starting cash balance via a dummy sales transaction
        initial_transactions.append({
            "item_name": None,
            "transaction_type": "sales",
            "units": None,
            "price": 50000.0,
            "transaction_date": initial_date,
        })

        # Add one stock order transaction per inventory item
        for _, item in inventory_df.iterrows():
            initial_transactions.append({
                "item_name": item["item_name"],
                "transaction_type": "stock_orders",
                "units": item["current_stock"],
                "price": item["current_stock"] * item["unit_price"],
                "transaction_date": initial_date,
            })

        # Commit transactions to database
        pd.DataFrame(initial_transactions).to_sql("transactions", db_engine, if_exists="append", index=False)

        # Save the inventory reference table
        inventory_df.to_sql("inventory", db_engine, if_exists="replace", index=False)

        return db_engine

    except Exception as e:
        print(f"Error initializing database: {e}")
        raise

def create_transaction(
    item_name: str,
    transaction_type: str,
    quantity: int,
    price: float,
    date: Union[str, datetime],
    engine: Engine | None = None,
) -> int:
    """
    This function records a transaction of type 'stock_orders' or 'sales' with a specified
    item name, quantity, total price, and transaction date into the 'transactions' table of the database.

    Args:
        item_name (str): The name of the item involved in the transaction.
        transaction_type (str): Either 'stock_orders' or 'sales'.
        quantity (int): Number of units involved in the transaction.
        price (float): Total price of the transaction.
        date (str or datetime): Date of the transaction in ISO 8601 format.

    Returns:
        int: The ID of the newly inserted transaction.

    Raises:
        ValueError: If `transaction_type` is not 'stock_orders' or 'sales'.
        Exception: For other database or execution errors.
    """
    try:
        active_engine = engine if engine is not None else db_engine

        # Convert datetime to ISO string if necessary
        date_str = date.isoformat() if isinstance(date, datetime) else date

        # Validate transaction type
        if transaction_type not in {"stock_orders", "sales"}:
            raise ValueError("Transaction type must be 'stock_orders' or 'sales'")

        # Prepare transaction record as a single-row DataFrame
        transaction = pd.DataFrame([{
            "item_name": item_name,
            "transaction_type": transaction_type,
            "units": quantity,
            "price": price,
            "transaction_date": date_str,
        }])

        # Insert the record into the database
        transaction.to_sql("transactions", active_engine, if_exists="append", index=False)

        # Fetch and return the ID of the inserted row
        result = pd.read_sql("SELECT last_insert_rowid() as id", active_engine)
        return int(result.iloc[0]["id"])

    except Exception as e:
        print(f"Error creating transaction: {e}")
        raise

def get_all_inventory(
    as_of_date: str,
    engine: Engine | None = None,
) -> Dict[str, int]:
    """
    Retrieve a snapshot of available inventory as of a specific date.

    This function calculates the net quantity of each item by summing 
    all stock orders and subtracting all sales up to and including the given date.

    Only items with positive stock are included in the result.

    Args:
        as_of_date (str): ISO-formatted date string (YYYY-MM-DD) representing the inventory cutoff.

    Returns:
        Dict[str, int]: A dictionary mapping item names to their current stock levels.
    """
    # SQL query to compute stock levels per item as of the given date
    operator, cutoff = _transaction_cutoff(as_of_date)
    query = f"""
        SELECT
            item_name,
            SUM(CASE
                WHEN transaction_type = 'stock_orders' THEN units
                WHEN transaction_type = 'sales' THEN -units
                ELSE 0
            END) as stock
        FROM transactions
        WHERE item_name IS NOT NULL
        AND transaction_date {operator} :cutoff
        GROUP BY item_name
        HAVING stock > 0
    """

    # Execute the query with the date parameter
    active_engine = engine if engine is not None else db_engine
    result = pd.read_sql(query, active_engine, params={"cutoff": cutoff})

    # Convert the result into a dictionary {item_name: stock}
    return dict(zip(result["item_name"], result["stock"]))

def get_stock_level(
    item_name: str,
    as_of_date: Union[str, datetime],
    engine: Engine | None = None,
) -> pd.DataFrame:
    """
    Retrieve the stock level of a specific item as of a given date.

    This function calculates the net stock by summing all 'stock_orders' and 
    subtracting all 'sales' transactions for the specified item up to the given date.

    Args:
        item_name (str): The name of the item to look up.
        as_of_date (str or datetime): The cutoff date (inclusive) for calculating stock.

    Returns:
        pd.DataFrame: A single-row DataFrame with columns 'item_name' and 'current_stock'.
    """
    # SQL query to compute net stock level for the item
    operator, cutoff = _transaction_cutoff(as_of_date)
    stock_query = f"""
        SELECT
            item_name,
            COALESCE(SUM(CASE
                WHEN transaction_type = 'stock_orders' THEN units
                WHEN transaction_type = 'sales' THEN -units
                ELSE 0
            END), 0) AS current_stock
        FROM transactions
        WHERE item_name = :item_name
        AND transaction_date {operator} :cutoff
    """

    # Execute query and return result as a DataFrame
    active_engine = engine if engine is not None else db_engine
    return pd.read_sql(
        stock_query,
        active_engine,
        params={"item_name": item_name, "cutoff": cutoff},
    )

def get_supplier_delivery_date(input_date_str: str, quantity: int) -> str:
    """
    Estimate the supplier delivery date based on the requested order quantity and a starting date.

    Delivery lead time increases with order size:
        - ≤10 units: same day
        - 11–100 units: 1 day
        - 101–1000 units: 4 days
        - >1000 units: 7 days

    Args:
        input_date_str (str): The starting date in ISO format (YYYY-MM-DD).
        quantity (int): The number of units in the order.

    Returns:
        str: Estimated delivery date in ISO format (YYYY-MM-DD).
    """
    # Debug log (comment out in production if needed)
    print(f"FUNC (get_supplier_delivery_date): Calculating for qty {quantity} from date string '{input_date_str}'")

    # Attempt to parse the input date
    try:
        input_date_dt = datetime.fromisoformat(input_date_str.split("T")[0])
    except (ValueError, TypeError):
        # Fallback to current date on format error
        print(f"WARN (get_supplier_delivery_date): Invalid date format '{input_date_str}', using today as base.")
        input_date_dt = datetime.now()

    # Determine delivery delay based on quantity
    if quantity <= 10:
        days = 0
    elif quantity <= 100:
        days = 1
    elif quantity <= 1000:
        days = 4
    else:
        days = 7

    # Add delivery days to the starting date
    delivery_date_dt = input_date_dt + timedelta(days=days)

    # Return formatted delivery date
    return delivery_date_dt.strftime("%Y-%m-%d")

def get_cash_balance(
    as_of_date: Union[str, datetime],
    engine: Engine | None = None,
) -> float:
    """
    Calculate the current cash balance as of a specified date.

    The balance is computed by subtracting total stock purchase costs ('stock_orders')
    from total revenue ('sales') recorded in the transactions table up to the given date.

    Args:
        as_of_date (str or datetime): The cutoff date (inclusive) in ISO format or as a datetime object.

    Returns:
        float: Net cash balance as of the given date. Returns 0.0 if no transactions exist or an error occurs.
    """
    try:
        # Query all transactions on or before the specified date
        operator, cutoff = _transaction_cutoff(as_of_date)
        active_engine = engine if engine is not None else db_engine
        transactions = pd.read_sql(
            f"SELECT * FROM transactions WHERE transaction_date {operator} :cutoff",
            active_engine,
            params={"cutoff": cutoff},
        )

        # Compute the difference between sales and stock purchases
        if not transactions.empty:
            total_sales = transactions.loc[transactions["transaction_type"] == "sales", "price"].sum()
            total_purchases = transactions.loc[transactions["transaction_type"] == "stock_orders", "price"].sum()
            return float(total_sales - total_purchases)

        return 0.0

    except Exception as e:
        print(f"Error getting cash balance: {e}")
        return 0.0


def generate_financial_report(
    as_of_date: Union[str, datetime],
    engine: Engine | None = None,
) -> Dict:
    """
    Generate a complete financial report for the company as of a specific date.

    This includes:
    - Cash balance
    - Inventory valuation
    - Combined asset total
    - Itemized inventory breakdown
    - Top 5 best-selling products

    Args:
        as_of_date (str or datetime): The date (inclusive) for which to generate the report.

    Returns:
        Dict: A dictionary containing the financial report fields:
            - 'as_of_date': The date of the report
            - 'cash_balance': Total cash available
            - 'inventory_value': Total value of inventory
            - 'total_assets': Combined cash and inventory value
            - 'inventory_summary': List of items with stock and valuation details
            - 'top_selling_products': List of top 5 products by revenue
    """
    active_engine = engine if engine is not None else db_engine
    report_date = as_of_date.isoformat() if isinstance(as_of_date, datetime) else as_of_date

    # Get current cash balance
    cash = get_cash_balance(as_of_date, engine=active_engine)

    # Get current inventory snapshot
    inventory_df = pd.read_sql("SELECT * FROM inventory", active_engine)
    inventory_value = 0.0
    inventory_summary = []

    # Compute total inventory value and summary by item
    for _, item in inventory_df.iterrows():
        stock_info = get_stock_level(
            item["item_name"],
            as_of_date,
            engine=active_engine,
        )
        stock = stock_info["current_stock"].iloc[0]
        item_value = stock * item["unit_price"]
        inventory_value += item_value

        inventory_summary.append({
            "item_name": item["item_name"],
            "stock": stock,
            "unit_price": item["unit_price"],
            "value": item_value,
        })

    # Identify top-selling products by revenue
    operator, cutoff = _transaction_cutoff(as_of_date)
    top_sales_query = f"""
        SELECT item_name, SUM(units) as total_units, SUM(price) as total_revenue
        FROM transactions
        WHERE transaction_type = 'sales'
          AND item_name IS NOT NULL AND units IS NOT NULL
          AND transaction_date {operator} :cutoff
        GROUP BY item_name
        ORDER BY total_revenue DESC
        LIMIT 5
    """
    top_sales = pd.read_sql(
        top_sales_query,
        active_engine,
        params={"cutoff": cutoff},
    )
    top_selling_products = top_sales.to_dict(orient="records")

    return {
        "as_of_date": report_date,
        "cash_balance": cash,
        "inventory_value": inventory_value,
        "total_assets": cash + inventory_value,
        "inventory_summary": inventory_summary,
        "top_selling_products": top_selling_products,
    }


def search_quote_history(
    search_terms: List[str],
    limit: int = 5,
    engine: Engine | None = None,
) -> List[Dict]:
    """
    Retrieve a list of historical quotes that match any of the provided search terms.

    The function searches both the original customer request (from `quote_requests`) and
    the explanation for the quote (from `quotes`) for each keyword. Results are sorted by
    most recent order date and limited by the `limit` parameter.

    Args:
        search_terms (List[str]): List of terms to match against customer requests and explanations.
        limit (int, optional): Maximum number of quote records to return. Default is 5.

    Returns:
        List[Dict]: A list of matching quotes, each represented as a dictionary with fields:
            - original_request
            - total_amount
            - quote_explanation
            - job_type
            - order_size
            - event_type
            - order_date
    """
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer")

    conditions = []
    params = {}

    # Build SQL WHERE clause using LIKE filters for each search term
    for i, term in enumerate(search_terms):
        param_name = f"term_{i}"
        conditions.append(
            f"(LOWER(qr.response) LIKE :{param_name} OR "
            f"LOWER(q.quote_explanation) LIKE :{param_name})"
        )
        params[param_name] = f"%{term.lower()}%"

    # Combine conditions; fallback to always-true if no terms provided
    where_clause = " OR ".join(conditions) if conditions else "1=1"

    # Final SQL query to join quotes with quote_requests
    query = f"""
        SELECT
            qr.response AS original_request,
            q.total_amount,
            q.quote_explanation,
            q.job_type,
            q.order_size,
            q.event_type,
            q.order_date
        FROM quotes q
        JOIN quote_requests qr ON q.request_id = qr.id
        WHERE {where_clause}
        ORDER BY q.order_date DESC
        LIMIT :limit
    """

    # Execute parameterized query
    params["limit"] = limit
    active_engine = engine if engine is not None else db_engine
    with active_engine.connect() as conn:
        result = conn.execute(text(query), params)
        return [dict(row._mapping) for row in result]

########################
########################
########################
# YOUR MULTI AGENT STARTS HERE
########################
########################
########################


# Set up and load environment parameters and instantiate the model.
def build_model() -> OpenAIChatModel:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")

    api_key = os.getenv("UDACITY_OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")
    model_name = os.getenv("MODEL_NAME")

    missing = [
        name for name, value in (
            ("UDACITY_OPENAI_API_KEY", api_key),
            ("OPENAI_BASE_URL", base_url),
            ("MODEL_NAME", model_name),
        )
        if not value
    ]
    if missing:
        raise RuntimeError("Missing configuration:\n" + "\n".join(missing))


    return OpenAIChatModel(
        model_name,
        provider=OpenAIProvider(api_key=api_key, base_url=base_url),
    )


"""Set up tools for your agents to use, these should be methods that combine the database functions above
 and apply criteria to them to ensure that the flow of the system is correct."""


# Tools for inventory agent
class InventoryDeps:
    """Values supplied separately for each inventory-agent request."""

    def __init__(
        self,
        engine: Engine,
        as_of_date: str,
        allow_reorder: bool = False,
        allow_stock_receipt: bool = False,
        allow_financial_report: bool = False,
        request_id: str | None = None,
    ):
        self.engine = engine
        self.as_of_date = as_of_date
        self.allow_reorder = allow_reorder
        self.allow_stock_receipt = allow_stock_receipt
        self.allow_financial_report = allow_financial_report
        self.request_id = request_id
    
class InventoryStatus(BaseModel):
    item_name: str
    found: bool
    available: int
    min_stock_level: int | None
    pending: int
    recommended_order: int

def ensure_purchase_orders_schema(engine: Engine) -> None:
    """
    Create the table used to track supplies orders not yet received.
    """
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS purchase_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT NOT NULL UNIQUE,
                item_name TEXT NOT NULL,
                quantity INTEGER NOT NULL CHECK (quantity > 0),
                estimated_cost REAL NOT NULL,
                created_date TEXT NOT NULL,
                expected_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending'
            )
        """))

def _next_day(as_of_date: str) -> str:
    """Exclusive cutoff that includes transactions at any time on this date."""
    day = datetime.strptime(as_of_date, "%Y-%m-%d")
    return (day + timedelta(days=1)).strftime("%Y-%m-%d")

def _inventory_snapshot(connection, item_name: str, as_of_date: str):
    """Read stock and pending orders using an existing DB connection."""
    item = connection.execute(
        text("""
            SELECT item_name, min_stock_level, unit_price
            FROM inventory
            WHERE LOWER(item_name) = LOWER(:item_name)
        """),
        {"item_name": item_name.strip()},
    ).mappings().first()

    if item is None:
        return InventoryStatus(
            item_name=item_name,
            found=False,
            available=0,
            min_stock_level=None,
            pending=0,
            recommended_order=0,
        ), 0.0

    actual_name = item["item_name"]

    available = int(connection.execute(
        text("""
            SELECT COALESCE(SUM(
                CASE
                    WHEN transaction_type = 'stock_orders' THEN units
                    WHEN transaction_type = 'sales' THEN -units
                    ELSE 0
                END
            ), 0)
            FROM transactions
            WHERE item_name = :item_name
              AND transaction_date < :cutoff
        """),
        {
            "item_name": actual_name,
            "cutoff": _next_day(as_of_date),
        },
    ).scalar_one())

    pending = int(connection.execute(
        text("""
            SELECT COALESCE(SUM(quantity), 0)
            FROM purchase_orders
            WHERE item_name = :item_name
              AND status = 'pending'
              AND created_date <= :as_of_date
        """),
        {
            "item_name": actual_name,
            "as_of_date": as_of_date,
        },
    ).scalar_one())

    minimum = int(item["min_stock_level"])

    # When below the minimum, aim for twice that minimum.
    # Pending orders are counted so we do not repeatedly order the same stock.
    recommended = (
        max(2 * minimum - available - pending, 0)
        if available < minimum
        else 0
    )

    status = InventoryStatus(
        item_name=actual_name,
        found=True,
        available=available,
        min_stock_level=minimum,
        pending=pending,
        recommended_order=recommended,
    )

    return status, float(item["unit_price"])


def inventory_status(
    engine: Engine,
    item_name: str,
    as_of_date: str,
) -> InventoryStatus:
    """Read inventory without placing an order."""
    with engine.connect() as connection:
        status, _ = _inventory_snapshot(
            connection, item_name, as_of_date
        )
        return status


def place_pending_reorder(
    engine: Engine,
    item_name: str,
    as_of_date: str,
    request_id: str,
) -> dict:
    """Create one pending purchase order if stock is low and cash permits."""
    if not request_id.strip():
        raise ValueError("request_id is required for reorders")

    with engine.begin() as connection:
        existing = connection.execute(
            text("""
                SELECT id, item_name, quantity
                FROM purchase_orders
                WHERE request_id = :request_id
            """),
            {"request_id": request_id},
        ).mappings().first()

        if existing is not None:
            if existing["item_name"].lower() != item_name.lower():
                raise ValueError(
                    "request_id has already been used for another item"
                )
            return {
                "status": "already_created",
                "order_id": existing["id"],
                "quantity": existing["quantity"],
            }

        stock, unit_price = _inventory_snapshot(
            connection, item_name, as_of_date
        )

        if not stock.found:
            return {"status": "unknown_item"}

        if stock.recommended_order == 0:
            return {"status": "no_reorder_needed"}

        quantity = stock.recommended_order

        # The starter has no supplier-cost field. Treat unit_price as an
        # estimated purchase cost until supplier pricing is available.
        estimated_cost = round(quantity * unit_price, 2)

        cash = float(connection.execute(
            text("""
                SELECT COALESCE(SUM(
                    CASE
                        WHEN transaction_type = 'sales' THEN price
                        WHEN transaction_type = 'stock_orders' THEN -price
                        ELSE 0
                    END
                ), 0)
                FROM transactions
                WHERE transaction_date < :cutoff
            """),
            {"cutoff": _next_day(as_of_date)},
        ).scalar_one())

        committed = float(connection.execute(
            text("""
                SELECT COALESCE(SUM(estimated_cost), 0)
                FROM purchase_orders
                WHERE status = 'pending'
                  AND created_date <= :as_of_date
            """),
            {"as_of_date": as_of_date},
        ).scalar_one())

        available_cash = cash - committed
        if available_cash < estimated_cost:
            return {
                "status": "insufficient_cash",
                "required": estimated_cost,
                "available_cash": round(available_cash, 2),
            }

        expected_date = get_supplier_delivery_date(
            as_of_date, quantity
        )

        inserted = connection.execute(
            text("""
                INSERT INTO purchase_orders
                    (request_id, item_name, quantity, estimated_cost,
                     created_date, expected_date, status)
                VALUES
                    (:request_id, :item_name, :quantity, :cost,
                     :created_date, :expected_date, 'pending')
            """),
            {
                "request_id": request_id,
                "item_name": stock.item_name,
                "quantity": quantity,
                "cost": estimated_cost,
                "created_date": as_of_date,
                "expected_date": expected_date,
            },
        )

        return {
            "status": "created",
            "order_id": inserted.lastrowid,
            "quantity": quantity,
            "estimated_cost": estimated_cost,
            "expected_date": expected_date,
        }


def make_inventory_agent(model) -> Agent:
    inventory_agent = Agent(
        model,
        deps_type=InventoryDeps,
        instructions=(
            "Use inventory_lookup for one product and inventory_overview "
            "for a company-wide stock snapshot. "
            "Use supplier_delivery_date only for delivery estimates. "
            "Use cash_balance or financial_report only for an authorized "
            "management request; the tools enforce this permission. "
            "Use only quantities returned by tools. "
            "For low stock, mention the recommended reorder quantity. "
            "Call request_reorder only for an explicit reorder request. "
            "Call record_stock_receipt only for an explicitly authorized "
            "receipt of supplier stock. "
            "A pending purchase order is not available stock."
        ),
    )

    @inventory_agent.tool
    def inventory_lookup(
        ctx: RunContext[InventoryDeps],
        item_name: str,
    ) -> dict:
        """Check stock and calculate a reorder recommendation."""
        stock_frame = get_stock_level(
            item_name,
            ctx.deps.as_of_date,
            engine=ctx.deps.engine,
        )
        status = inventory_status(
            ctx.deps.engine,
            item_name,
            ctx.deps.as_of_date,
        )
        result = status.model_dump()
        result["current_stock"] = int(
            stock_frame.iloc[0]["current_stock"]
        )
        return result

    @inventory_agent.tool
    def inventory_overview(ctx: RunContext[InventoryDeps]) -> dict[str, int]:
        """Return all positive stock balances as of the request date."""
        snapshot = get_all_inventory(
            ctx.deps.as_of_date,
            engine=ctx.deps.engine,
        )
        return {item_name: int(stock) for item_name, stock in snapshot.items()}

    @inventory_agent.tool
    def supplier_delivery_date(
        ctx: RunContext[InventoryDeps],
        quantity: int,
    ) -> str:
        """Estimate a supplier delivery date for a positive quantity."""
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        return get_supplier_delivery_date(ctx.deps.as_of_date, quantity)

    @inventory_agent.tool
    def cash_balance(ctx: RunContext[InventoryDeps]) -> dict:
        """Return cash data only for an authorized management request."""
        if not ctx.deps.allow_financial_report:
            return {
                "status": "not_authorized",
                "reason": "Financial data requires management authorization.",
            }
        return {
            "status": "authorized",
            "as_of_date": ctx.deps.as_of_date,
            "cash_balance": get_cash_balance(
                ctx.deps.as_of_date,
                engine=ctx.deps.engine,
            ),
        }

    @inventory_agent.tool
    def financial_report(ctx: RunContext[InventoryDeps]) -> dict:
        """Return the full financial and inventory report."""
        if not ctx.deps.allow_financial_report:
            return {
                "status": "not_authorized",
                "reason": "Financial data requires management authorization.",
            }
        return generate_financial_report(
            ctx.deps.as_of_date,
            engine=ctx.deps.engine,
        )

    @inventory_agent.tool
    def request_reorder(
        ctx: RunContext[InventoryDeps],
        item_name: str,
    ) -> dict:
        """Place a pending reorder only when the workflow authorizes it."""
        if not ctx.deps.allow_reorder or not ctx.deps.request_id:
            return {"status": "not_authorized"}

        return place_pending_reorder(
            ctx.deps.engine,
            item_name,
            ctx.deps.as_of_date,
            ctx.deps.request_id,
        )

    @inventory_agent.tool
    def record_stock_receipt(
        ctx: RunContext[InventoryDeps],
        item_name: str,
        quantity: int,
        total_price: float,
    ) -> dict:
        """Record received supplier stock only with caller authorization."""
        if not ctx.deps.allow_stock_receipt:
            return {"status": "not_authorized"}
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        if total_price < 0:
            raise ValueError("total_price cannot be negative")

        stock = inventory_status(
            ctx.deps.engine,
            item_name,
            ctx.deps.as_of_date,
        )
        if not stock.found:
            return {"status": "unknown_item", "item_name": item_name}

        transaction_id = create_transaction(
            stock.item_name,
            "stock_orders",
            quantity,
            total_price,
            ctx.deps.as_of_date,
            engine=ctx.deps.engine,
        )
        return {
            "status": "recorded",
            "transaction_id": transaction_id,
            "item_name": stock.item_name,
            "quantity": quantity,
            "total_price": total_price,
        }

    return inventory_agent


def answer_inventory_question(
    message: str,
    request_date: str,
    *,
    allow_reorder: bool = False,
    allow_stock_receipt: bool = False,
    allow_financial_report: bool = False,
    request_id: str | None = None,
    engine: Engine | None = None,
    model=None,
) -> str:
    """Run one inventory request after the database has been initialized."""
    active_engine = engine if engine is not None else db_engine
    ensure_purchase_orders_schema(active_engine)

    # Passing a fake model here lets unit tests avoid a real API call.
    active_model = model if model is not None else build_model()
    inventory_agent = make_inventory_agent(active_model)

    deps = InventoryDeps(
        engine=active_engine,
        as_of_date=request_date,
        allow_reorder=allow_reorder,
        allow_stock_receipt=allow_stock_receipt,
        allow_financial_report=allow_financial_report,
        request_id=request_id,
    )

    result = inventory_agent.run_sync(message, deps=deps)
    return result.output
    
# Tools for quoting agent
CENT = Decimal("0.01")


class QuoteItemRequest(BaseModel):
    item_name: str
    quantity: int = Field(gt=0, le=1_000_000)
    unit: Literal["sheet", "ream", "unit", "box"]


class QuoteRequest(BaseModel):
    items: list[QuoteItemRequest] = Field(min_length=1)


class QuotedLine(BaseModel):
    item_name: str
    quantity: int                 # Quantity in catalog pricing units
    available: int
    backordered: int
    unit_price: Decimal
    discount_percent: int
    line_total: Decimal
    supplier_eta: str | None
    historical_examples: list[dict]


class PreparedQuote(BaseModel):
    quote_id: str
    request_date: str
    expires_on: str
    status: Literal["ready", "backorder_required"]
    lines: list[QuotedLine]
    total: Decimal


class QuoteDeps:
    def __init__(self, engine: Engine, as_of_date: str):
        self.engine = engine
        self.as_of_date = as_of_date


def ensure_generated_quotes_schema(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS generated_quotes (
                quote_id TEXT PRIMARY KEY,
                request_id TEXT UNIQUE,
                request_date TEXT NOT NULL,
                expires_on TEXT NOT NULL,
                status TEXT NOT NULL,
                total TEXT NOT NULL,
                payload TEXT NOT NULL
            )
        """))


def save_prepared_quote(
    engine: Engine,
    quote: PreparedQuote,
    request_id: str | None,
) -> str:
    """Persist one deterministic quote and return its JSON payload."""
    ensure_generated_quotes_schema(engine)
    payload = quote.model_dump_json(indent=2)
    with engine.begin() as connection:
        connection.execute(
            text("""
                INSERT INTO generated_quotes
                    (quote_id, request_id, request_date, expires_on,
                     status, total, payload)
                VALUES
                    (:quote_id, :request_id, :request_date, :expires_on,
                     :status, :total, :payload)
            """),
            {
                "quote_id": quote.quote_id,
                "request_id": request_id,
                "request_date": quote.request_date,
                "expires_on": quote.expires_on,
                "status": quote.status,
                "total": str(quote.total),
                "payload": payload,
            },
        )
    return payload


def related_quote_history(
    engine: Engine,
    item_name: str,
    limit: int = 2,
) -> list[dict]:
    """Historical whole-order quotes, for context rather than unit pricing."""
    with engine.connect() as connection:
        rows = connection.execute(
            text("""
                SELECT
                    qr.response AS original_request,
                    q.total_amount,
                    q.quote_explanation
                FROM quotes AS q
                JOIN quote_requests AS qr
                  ON qr.id = q.request_id
                WHERE LOWER(qr.response) LIKE :term
                   OR LOWER(q.quote_explanation) LIKE :term
                ORDER BY q.order_date DESC
                LIMIT :limit
            """),
            {
                "term": f"%{item_name.lower()}%",
                "limit": limit,
            },
        ).mappings().all()

    return [dict(row) for row in rows]


def _catalog_item(item_name: str) -> dict | None:
    return next(
        (
            item
            for item in paper_supplies
            if item["item_name"].casefold() == item_name.strip().casefold()
        ),
        None,
    )


def _pricing_quantity(requested: QuoteItemRequest, item: dict) -> int:
    """Convert the customer's unit to the catalog's pricing unit."""
    if requested.unit == "box":
        raise ValueError(
            f"Specify how many units are in a box of {item['item_name']}."
        )

    if requested.unit == "ream":
        if item["category"] not in {"paper", "specialty"}:
            raise ValueError(
                f"{item['item_name']} cannot be quoted in reams."
            )
        return requested.quantity * 500

    if requested.unit == "sheet" and item["category"] not in {
        "paper", "specialty"
    }:
        raise ValueError(
            f"{item['item_name']} is priced per unit, not per sheet."
        )

    return requested.quantity


def _bulk_discount(quantity: int) -> int:
    if quantity >= 500:
        return 10
    if quantity >= 100:
        return 5
    return 0


def calculate_quote(
    request: QuoteRequest,
    engine: Engine,
    request_date: str,
) -> PreparedQuote:
    """Validate products and calculate a quote without changing inventory."""
    request_day = datetime.strptime(request_date, "%Y-%m-%d")
    lines: list[QuotedLine] = []
    normalized_lines: list[tuple[dict, int]] = []

    for requested in request.items:
        item = _catalog_item(requested.item_name)
        if item is None:
            raise ValueError(
                f"Unknown catalog item: {requested.item_name}. "
                "Ask the customer to clarify the exact product."
            )

        quantity = _pricing_quantity(requested, item)
        normalized_lines.append((item, quantity))

    # Allocate on-hand stock across all lines for the same product. A quote
    # must not be marked ready when duplicate lines exceed available stock.
    remaining_stock: dict[str, int] = {}
    for item, quantity in normalized_lines:
        name = item["item_name"]
        if name not in remaining_stock:
            stock = inventory_status(engine, name, request_date)
            remaining_stock[name] = max(stock.available, 0) if stock.found else 0

        available = min(remaining_stock[name], quantity)
        remaining_stock[name] -= available
        backordered = quantity - available

        unit_price = Decimal(str(item["unit_price"]))
        discount = _bulk_discount(quantity)
        line_total = (
            unit_price
            * quantity
            * (Decimal("100") - discount)
            / Decimal("100")
        ).quantize(CENT, rounding=ROUND_HALF_UP)

        supplier_eta = (
            get_supplier_delivery_date(request_date, backordered)
            if backordered
            else None
        )

        lines.append(
            QuotedLine(
                item_name=name,
                quantity=quantity,
                available=available,
                backordered=backordered,
                unit_price=unit_price,
                discount_percent=discount,
                line_total=line_total,
                supplier_eta=supplier_eta,
                historical_examples=related_quote_history(
                    engine, item["item_name"]
                ),
            )
        )

    total = sum(
        (line.line_total for line in lines),
        start=Decimal("0.00"),
    )

    return PreparedQuote(
        quote_id=str(uuid4()),
        request_date=request_date,
        expires_on=(request_day + timedelta(days=7)).strftime("%Y-%m-%d"),
        status=(
            "backorder_required"
            if any(line.backordered for line in lines)
            else "ready"
        ),
        lines=lines,
        total=total,
    )


def make_quotation_agent(model) -> Agent:
    quotation_agent = Agent(
        model,
        deps_type=QuoteDeps,
        output_type=QuoteRequest,
        instructions=(
            "Extract every requested product, quantity, and unit. "
            "Use catalog_items to identify exact product names and "
            "quote_context for stock and historical context. "
            "Use search_historical_quotes when additional comparable "
            "quotes are needed. "
            "Do not calculate prices yourself. "
            "Do not invent a product that is absent from the catalog. "
            "Use 'ream' when the customer requests reams and 'box' "
            "when the customer requests boxes."
        ),
    )

    @quotation_agent.tool
    def catalog_items(ctx: RunContext[QuoteDeps]) -> list[str]:
        """List products that can be quoted."""
        return [item["item_name"] for item in paper_supplies]

    @quotation_agent.tool
    def quote_context(
        ctx: RunContext[QuoteDeps],
        item_name: str,
    ) -> dict:
        """Read stock and comparable historical quotes for an item."""
        item = _catalog_item(item_name)
        if item is None:
            return {"found": False, "item_name": item_name}

        stock = inventory_status(
            ctx.deps.engine,
            item["item_name"],
            ctx.deps.as_of_date,
        )
        return {
            "found": True,
            "item_name": item["item_name"],
            "list_price": item["unit_price"],
            "stock": stock.model_dump(),
            "historical_examples": related_quote_history(
                ctx.deps.engine, item["item_name"]
            ),
        }

    @quotation_agent.tool
    def search_historical_quotes(
        ctx: RunContext[QuoteDeps],
        search_terms: list[str],
        limit: int = 5,
    ) -> list[dict]:
        """Search prior customer requests and quote explanations."""
        return search_quote_history(
            search_terms,
            limit=limit,
            engine=ctx.deps.engine,
        )

    return quotation_agent


def answer_quote_request(
    message: str,
    request_date: str,
    *,
    request_id: str | None = None,
    engine: Engine | None = None,
    model=None,
) -> str:
    """Extract, calculate, save, and return a text-based quotation."""
    active_engine = engine if engine is not None else db_engine

    # Set up tables once; this does not place a supplier order.
    ensure_purchase_orders_schema(active_engine)
    ensure_generated_quotes_schema(active_engine)

    if request_id is not None:
        with active_engine.connect() as connection:
            previous = connection.execute(
                text("""
                    SELECT payload
                    FROM generated_quotes
                    WHERE request_id = :request_id
                """),
                {"request_id": request_id},
            ).scalar_one_or_none()
        if previous is not None:
            stored_quote = PreparedQuote.model_validate_json(previous)
            return customer_quote_response(stored_quote)

    active_model = model if model is not None else build_model()
    agent = make_quotation_agent(active_model)

    extracted = agent.run_sync(
        message,
        deps=QuoteDeps(active_engine, request_date),
    ).output

    try:
        quote = calculate_quote(
            extracted, active_engine, request_date
        )
    except ValueError as exc:
        return f"Clarification needed: {exc}"

    save_prepared_quote(active_engine, quote, request_id)
    return customer_quote_response(quote)

# Tools for ordering agent
import json


class QuoteAcceptance(BaseModel):
    quote_id: str | None = None
    confirmed: bool


class OrderingDeps:
    def __init__(self, engine: Engine):
        self.engine = engine


def ensure_sales_orders_schema(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS sales_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                quote_id TEXT NOT NULL UNIQUE,
                order_date TEXT NOT NULL,
                estimated_dispatch_date TEXT NOT NULL,
                total TEXT NOT NULL,
                status TEXT NOT NULL
            )
        """))
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS sales_order_lines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                item_name TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                line_total TEXT NOT NULL
            )
        """))


def _estimated_dispatch_date(order_date: str) -> str:
    """Estimate dispatch on the next weekday; this is not delivery."""
    dispatch = datetime.strptime(order_date, "%Y-%m-%d")
    dispatch += timedelta(days=1)

    while dispatch.weekday() >= 5:
        dispatch += timedelta(days=1)

    return dispatch.strftime("%Y-%m-%d")


def finalize_sale(
    engine: Engine,
    quote_id: str,
    order_date: str,
) -> dict:
    """
    Confirm a quote, recheck stock, and record the sale atomically.

    Does not call create_transaction(), because that helper opens its own
    database connection and cannot share this transaction.
    """
    datetime.strptime(order_date, "%Y-%m-%d")

    if not quote_id.strip():
        return {"status": "missing_quote_id"}

    with engine.connect() as connection:
        try:
            # Acquire SQLite's write lock before checking stock. This keeps
            # the stock check and subsequent sales inserts together.
            connection.exec_driver_sql("BEGIN IMMEDIATE")

            def reject(status: str, **details) -> dict:
                connection.rollback()
                return {"status": status, **details}

            existing = connection.execute(
                text("""
                    SELECT id, quote_id, estimated_dispatch_date, total
                    FROM sales_orders
                    WHERE quote_id = :quote_id
                """),
                {"quote_id": quote_id},
            ).mappings().first()

            if existing is not None:
                return reject(
                    "already_confirmed",
                    order_id=existing["id"],
                    quote_id=existing["quote_id"],
                    estimated_dispatch_date=existing[
                        "estimated_dispatch_date"
                    ],
                    total=existing["total"],
                )

            stored = connection.execute(
                text("""
                    SELECT quote_id, request_date, expires_on,
                           status, total, payload
                    FROM generated_quotes
                    WHERE quote_id = :quote_id
                """),
                {"quote_id": quote_id},
            ).mappings().first()

            if stored is None:
                return reject("quote_not_found")

            if stored["status"] != "ready":
                return reject(
                    "quote_not_ready",
                    quote_status=stored["status"],
                )

            if order_date < stored["request_date"]:
                return reject("order_date_before_quote")

            if order_date > stored["expires_on"]:
                return reject("quote_expired")

            quote = PreparedQuote.model_validate_json(stored["payload"])

            if (
                quote.quote_id != quote_id
                or quote.status != "ready"
                or not quote.lines
                or quote.total != Decimal(stored["total"])
            ):
                return reject("invalid_quote_data")

            if sum(
                (line.line_total for line in quote.lines),
                Decimal("0.00"),
            ) != quote.total:
                return reject("invalid_quote_total")

            # Aggregate duplicate product lines before checking stock.
            required_by_item: dict[str, int] = {}

            for line in quote.lines:
                catalog_item = _catalog_item(line.item_name)

                if (
                    catalog_item is None
                    or line.quantity <= 0
                    or line.backordered != 0
                    or line.line_total < 0
                ):
                    return reject("invalid_quote_line")

                item_name = catalog_item["item_name"]
                required_by_item[item_name] = (
                    required_by_item.get(item_name, 0) + line.quantity
                )

            for item_name, required in required_by_item.items():
                available = int(connection.execute(
                    text("""
                        SELECT COALESCE(SUM(
                            CASE
                                WHEN transaction_type = 'stock_orders'
                                    THEN units
                                WHEN transaction_type = 'sales'
                                    THEN -units
                                ELSE 0
                            END
                        ), 0)
                        FROM transactions
                        WHERE item_name = :item_name
                          AND transaction_date < :cutoff
                    """),
                    {
                        "item_name": item_name,
                        "cutoff": _next_day(order_date),
                    },
                ).scalar_one())

                if available < required:
                    return reject(
                        "insufficient_stock",
                        item_name=item_name,
                        required=required,
                        available=available,
                    )

            dispatch_date = _estimated_dispatch_date(order_date)

            inserted_order = connection.execute(
                text("""
                    INSERT INTO sales_orders
                        (quote_id, order_date, estimated_dispatch_date,
                         total, status)
                    VALUES
                        (:quote_id, :order_date, :dispatch_date,
                         :total, 'confirmed')
                """),
                {
                    "quote_id": quote_id,
                    "order_date": order_date,
                    "dispatch_date": dispatch_date,
                    "total": str(quote.total),
                },
            )
            order_id = int(inserted_order.lastrowid)

            for line in quote.lines:
                connection.execute(
                    text("""
                        INSERT INTO sales_order_lines
                            (order_id, item_name, quantity, line_total)
                        VALUES
                            (:order_id, :item_name, :quantity, :line_total)
                    """),
                    {
                        "order_id": order_id,
                        "item_name": line.item_name,
                        "quantity": line.quantity,
                        "line_total": str(line.line_total),
                    },
                )

                # A sale reduces available inventory in the existing
                # transaction-based stock calculations.
                connection.execute(
                    text("""
                        INSERT INTO transactions
                            (item_name, transaction_type, units,
                             price, transaction_date)
                        VALUES
                            (:item_name, 'sales', :units,
                             :price, :order_date)
                    """),
                    {
                        "item_name": line.item_name,
                        "units": line.quantity,
                        "price": float(line.line_total),
                        "order_date": order_date,
                    },
                )

            updated = connection.execute(
                text("""
                    UPDATE generated_quotes
                    SET status = 'accepted'
                    WHERE quote_id = :quote_id AND status = 'ready'
                """),
                {"quote_id": quote_id},
            )
            if updated.rowcount != 1:
                raise RuntimeError("Quote status changed during fulfillment")

            connection.commit()
            return {
                "status": "confirmed",
                "order_id": order_id,
                "quote_id": quote_id,
                "total": str(quote.total),
                "estimated_dispatch_date": dispatch_date,
            }

        except Exception:
            connection.rollback()
            raise


def make_ordering_agent(model) -> Agent:
    ordering_agent = Agent(
        model,
        deps_type=OrderingDeps,
        output_type=QuoteAcceptance,
        instructions=(
            "Extract the quote ID from the customer's message. "
            "Set confirmed=true only when the customer explicitly "
            "accepts that quote. Use quote_details to check the quoted "
            "amount and status. Never invent a quote ID, price, stock "
            "quantity, or delivery promise."
        ),
    )

    @ordering_agent.tool
    def quote_details(
        ctx: RunContext[OrderingDeps],
        quote_id: str,
    ) -> dict:
        """Read stored quote details; this tool never creates an order."""
        with ctx.deps.engine.connect() as connection:
            row = connection.execute(
                text("""
                    SELECT quote_id, status, expires_on, total
                    FROM generated_quotes
                    WHERE quote_id = :quote_id
                """),
                {"quote_id": quote_id},
            ).mappings().first()

        return dict(row) if row is not None else {"status": "not_found"}

    return ordering_agent


def answer_order_request(
    message: str,
    order_date: str,
    *,
    allow_fulfillment: bool = False,
    engine: Engine | None = None,
    model=None,
) -> str:
    """Return a text response after an explicitly authorized acceptance."""
    if not allow_fulfillment:
        return customer_message(
            "confirmation_required",
            "Explicit customer acceptance is required before placing the order.",
        )

    active_engine = engine if engine is not None else db_engine
    ensure_generated_quotes_schema(active_engine)
    ensure_sales_orders_schema(active_engine)

    active_model = model if model is not None else build_model()
    ordering_agent = make_ordering_agent(active_model)

    acceptance = ordering_agent.run_sync(
        message,
        deps=OrderingDeps(active_engine),
    ).output

    if not acceptance.confirmed or not acceptance.quote_id:
        return customer_message(
            "confirmation_required",
            "Please explicitly accept a valid quote and include its quote ID.",
        )

    result = finalize_sale(
        active_engine,
        acceptance.quote_id,
        order_date,
    )
    return customer_fulfillment_response(result)

# Set up your agents and create an orchestration agent that will manage them.
class RouteDecision(BaseModel):
    intent: Literal[
        "inventory",
        "reorder",
        "quote",
        "accept_quote",
        "report",
        "clarify",
    ]
    item_name: str | None = None
    quote_id: str | None = None
    reason: str | None = None


def make_orchestrator_agent(model) -> Agent:
    return Agent(
        model,
        output_type=RouteDecision,
        instructions=(
            "Classify the customer's text request into exactly one intent. "
            "Use 'inventory' for questions about current stock. "
            "Use 'reorder' only for an explicit request to replenish the "
            "company's supplies, not for a customer wanting to buy paper. "
            "Use 'quote' for a new customer order, a price request, or "
            "a request to place an order without an accepted quote ID. "
            "Use 'accept_quote' only when the customer explicitly accepts "
            "an existing quote and supplies its quote ID. "
            "Use 'report' for a company-wide financial or inventory report. "
            "Use 'clarify' when the request cannot be classified safely. "
            "Extract item_name for inventory or reorder requests. "
            "Extract quote_id for accepted-quote requests. "
            "Never invent an item name or quote ID. "
            "Do not calculate prices or authorize database changes."
        ),
    )


def handle_customer_request(
    message: str,
    request_date: str,
    *,
    request_id: str | None = None,
    allow_reorder: bool = False,
    allow_fulfillment: bool = False,
    allow_financial_report: bool = False,
    engine: Engine | None = None,
    model=None,
    orchestrator=None,
) -> str:
    """
    Route one text request through the approved workflow.

    Authorization flags must come from the calling workflow, not from the
    router's output. Financial details are withheld unless explicitly allowed.
    """
    datetime.strptime(request_date, "%Y-%m-%d")
    active_engine = engine if engine is not None else db_engine

    active_model = model if model is not None else build_model()
    router = (
        orchestrator
        if orchestrator is not None
        else make_orchestrator_agent(active_model)
    )

    decision = router.run_sync(message).output

    if decision.intent == "clarify":
        return (
            "Please clarify your request. "
            + (decision.reason or "")
        ).strip()

    if decision.intent == "report":
        if not allow_financial_report:
            return customer_message(
                "not_authorized",
                "Financial reports are available only to authorized company staff.",
            )
        report = generate_financial_report(
            request_date,
            engine=active_engine,
        )
        return json.dumps(report, default=str)

    if decision.intent == "inventory":
        if not decision.item_name:
            return "Please specify which paper product you want to check."

        return answer_inventory_question(
            message,
            request_date,
            allow_reorder=False,
            allow_financial_report=allow_financial_report,
            engine=active_engine,
            model=active_model,
        )

    if decision.intent == "reorder":
        if not decision.item_name:
            return "Please specify which product needs replenishment."

        if not allow_reorder or not request_id:
            return customer_message(
                "confirmation_required",
                "Reordering requires staff authorization and a valid request ID.",
            )

        # The write is made by the deterministic inventory workflow.
        # The language model cannot choose a quantity or bypass cash checks.
        ensure_purchase_orders_schema(active_engine)

        stock = inventory_status(
            active_engine,
            decision.item_name,
            request_date,
        )
        if not stock.found:
            return customer_message(
                "unknown_item",
                "The requested product is not in the current catalog. "
                "Please provide an exact catalog product name.",
            )

        outcome = place_pending_reorder(
            active_engine,
            stock.item_name,
            request_date,
            request_id,
        )
        return json.dumps(outcome)

    if decision.intent == "quote":
        # "Place a new order" produces a quote first. It does not sell stock.
        return answer_quote_request(
            message,
            request_date,
            request_id=request_id,
            engine=active_engine,
            model=active_model,
        )

    if decision.intent == "accept_quote":
        quote_id = (decision.quote_id or "").strip()

        if not quote_id:
            return "Please provide the quote ID you are accepting."

        # The ID must occur in the customer's message, not only in
        # text generated by the router.
        if quote_id.casefold() not in message.casefold():
            return "Please state the quote ID you wish to accept."

        if not allow_fulfillment:
            return customer_message(
                "confirmation_required",
                "Explicit customer acceptance is required before placing the order.",
            )

        ensure_generated_quotes_schema(active_engine)
        ensure_sales_orders_schema(active_engine)

        # The sales agent independently checks the customer's acceptance.
        acceptance = make_ordering_agent(active_model).run_sync(
            message,
            deps=OrderingDeps(active_engine),
        ).output

        if (
            not acceptance.confirmed
            or acceptance.quote_id != quote_id
        ):
            return customer_message(
                "confirmation_required",
                "Please explicitly accept the same quote ID shown in your message.",
            )

        # Quote validity, stock, idempotency, and writes are checked
        # again inside finalize_sale's SQLite transaction.
        return customer_fulfillment_response(
            finalize_sale(active_engine, quote_id, request_date)
        )

    return "Please clarify your request."

# Run your test scenarios by writing them here. Make sure to keep track of them.

def replay_quote_response(
    prior_response: str,
    request_date: str,
    request_id: str,
    engine: Engine,
) -> str:
    """Recalculate a previously extracted quote without another model call."""
    try:
        prior_payload = json.loads(prior_response)
    except (json.JSONDecodeError, TypeError):
        explanation = str(prior_response).replace(
            "Clarification needed during replay:",
            "Clarification required:",
        )
        return explanation

    if not isinstance(prior_payload, dict):
        return customer_message(
            "clarification_required",
            "The request could not be interpreted. Please clarify the products and quantities.",
        )
    if not prior_payload.get("quote_id"):
        status = str(prior_payload.get("status") or "clarification_required")
        if status == "confirmation_required":
            return customer_message(
                status,
                "This request requires explicit staff authorization before it can be processed.",
            )
        return customer_message(
            status,
            str(
                prior_payload.get("reason")
                or "Please clarify the requested products and quantities."
            ),
        )

    try:
        extracted = QuoteRequest(items=[
            QuoteItemRequest(
                item_name=line["item_name"],
                quantity=int(line["quantity"]),
                unit="sheet",
            )
            for line in prior_payload.get("lines", [])
        ])
        quote = calculate_quote(extracted, engine, request_date)
    except (KeyError, TypeError, ValueError) as exc:
        return f"Clarification needed during replay: {exc}"

    save_prepared_quote(engine, quote, request_id)
    return customer_quote_response(quote)

def run_test_scenarios(
    *,
    engine: Engine | None = None,
    model=None,
    orchestrator=None,
    output_path: Path | str | None = None,
    replay_results_path: Path | str | None = None,
):
    """Evaluate every sample request and save auditable row-level results.

    The evaluation uses a fresh in-memory database by default and a fixed
    inventory seed. A ready quote is followed by an explicit simulated
    acceptance so the sales agent and atomic fulfillment workflow are also
    evaluated. Backordered, ambiguous, or rejected quotes remain unfulfilled.
    Pass replay_results_path to reuse earlier agent extraction outputs without
    sending the dataset to an external model endpoint.
    """
    print("Initializing evaluation database...")
    owns_engine = engine is None
    active_engine = (
        engine
        if engine is not None
        else create_engine("sqlite:///:memory:")
    )
    results_path = (
        Path(output_path)
        if output_path is not None
        else Path(__file__).with_name("test_results.csv")
    )

    try:
        # Seed 40 produces a repeatable mixture of fulfillable and
        # stock-constrained requests for this evaluation dataset.
        init_database(active_engine, seed=40)
        ensure_purchase_orders_schema(active_engine)
        ensure_generated_quotes_schema(active_engine)
        ensure_sales_orders_schema(active_engine)
        quote_requests_sample = pd.read_csv(
            Path(__file__).with_name("quote_requests_sample.csv")
        )
        parsed_dates = pd.to_datetime(
            quote_requests_sample["request_date"],
            format="%m/%d/%y",
            errors="coerce",
        )
        if parsed_dates.isna().any():
            bad_rows = [
                int(index) + 1
                for index in quote_requests_sample.index[parsed_dates.isna()]
            ]
            raise ValueError(f"Invalid request dates in rows: {bad_rows}")

        quote_requests_sample = quote_requests_sample.assign(
            request_date=parsed_dates,
            source_request_id=quote_requests_sample.index + 1,
        ).sort_values(
            ["request_date", "source_request_id"],
            kind="stable",
        )

        replay_responses = None
        if replay_results_path is not None:
            prior_results = pd.read_csv(Path(replay_results_path))
            response_column = (
                "quote_response"
                if "quote_response" in prior_results.columns
                else "response"
            )
            replay_responses = {
                int(row["request_id"]): str(row[response_column])
                for _, row in prior_results.iterrows()
            }
            active_model = None
            active_orchestrator = None
        else:
            active_model = model if model is not None else build_model()
            active_orchestrator = (
                orchestrator
                if orchestrator is not None
                else make_orchestrator_agent(active_model)
            )
        run_id = uuid4().hex
        results = []

        for _, row in quote_requests_sample.iterrows():
            request_id = int(row["source_request_id"])
            request_date = row["request_date"].strftime("%Y-%m-%d")
            before = generate_financial_report(
                request_date,
                engine=active_engine,
            )
            request_with_date = (
                f"{row['request']} (Date of request: {request_date})"
            )

            stable_request_id = f"sample-{run_id}-{request_id}"
            if replay_responses is not None:
                prior_response = replay_responses.get(request_id)
                if prior_response is None:
                    quote_response = "No prior agent output was available."
                else:
                    quote_response = replay_quote_response(
                        prior_response,
                        request_date,
                        stable_request_id,
                        active_engine,
                    )
            else:
                quote_response = handle_customer_request(
                    request_with_date,
                    request_date,
                    request_id=stable_request_id,
                    engine=active_engine,
                    model=active_model,
                    orchestrator=active_orchestrator,
                )

            quote_id = ""
            quote_status = "not_created"
            fulfillment_status = "not_fulfilled"
            reason = "The request did not produce a valid quote."
            fulfillment_response = ""

            try:
                quote_payload = json.loads(quote_response)
            except (json.JSONDecodeError, TypeError):
                reason = str(quote_response)
            else:
                if isinstance(quote_payload, dict):
                    quote_id = str(quote_payload.get("quote_id") or "")
                    quote_status = str(
                        quote_payload.get("status") or "not_created"
                    )
                    reason = str(
                        quote_payload.get("reason")
                        or f"Quote status: {quote_status}."
                    )

                    if quote_id and quote_status == "ready":
                        acceptance_message = (
                            f"I explicitly accept quote {quote_id}."
                        )
                        if replay_responses is not None:
                            fulfillment_response = customer_fulfillment_response(
                                finalize_sale(
                                    active_engine,
                                    quote_id,
                                    request_date,
                                )
                            )
                        else:
                            fulfillment_response = answer_order_request(
                                acceptance_message,
                                request_date,
                                allow_fulfillment=True,
                                engine=active_engine,
                                model=active_model,
                            )
                        try:
                            fulfillment_payload = json.loads(
                                fulfillment_response
                            )
                        except (json.JSONDecodeError, TypeError):
                            reason = str(fulfillment_response)
                        else:
                            fulfillment_status = str(
                                fulfillment_payload.get("status")
                                or "not_fulfilled"
                            )
                            if fulfillment_status == "confirmed":
                                reason = "Ready quote explicitly accepted and fulfilled."
                            else:
                                reason = str(
                                    fulfillment_payload.get("reason")
                                    or f"Fulfillment status: {fulfillment_status}."
                                )
                    elif quote_status == "backorder_required":
                        reason = "Insufficient stock; supplier backorder required."

            after = generate_financial_report(
                request_date,
                engine=active_engine,
            )
            cash_before = float(before["cash_balance"])
            cash_after = float(after["cash_balance"])
            cash_change = round(cash_after - cash_before, 2)
            fulfilled = fulfillment_status == "confirmed"

            results.append({
                "request_id": request_id,
                "request_date": request_date,
                "job": row["job"],
                "event": row["event"],
                "request": row["request"],
                "evaluation_mode": (
                    "replay_existing_agent_outputs"
                    if replay_responses is not None
                    else "live_multi_agent"
                ),
                "quote_id": quote_id,
                "quote_status": quote_status,
                "fulfillment_status": fulfillment_status,
                "fulfilled": fulfilled,
                "reason": reason,
                "cash_before": round(cash_before, 2),
                "cash_after": round(cash_after, 2),
                "cash_change": cash_change,
                "inventory_before": round(float(before["inventory_value"]), 2),
                "inventory_after": round(float(after["inventory_value"]), 2),
                "quote_response": quote_response,
                "fulfillment_response": fulfillment_response,
            })

            print(
                f"Request {request_id}: quote={quote_status}, "
                f"fulfillment={fulfillment_status}, "
                f"cash_change=${cash_change:.2f}"
            )

        results_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(results).to_csv(results_path, index=False)

        fulfilled_count = sum(row["fulfilled"] for row in results)
        cash_change_count = sum(
            row["cash_change"] != 0 for row in results
        )
        print("\n===== EVALUATION SUMMARY =====")
        print(f"Dataset requests evaluated: {len(results)}")
        print(f"Successfully fulfilled: {fulfilled_count}")
        print(f"Requests changing cash: {cash_change_count}")
        print(f"Unfulfilled: {len(results) - fulfilled_count}")
        print(f"Results saved to: {results_path.resolve()}")
        return results
    finally:
        if owns_engine:
            active_engine.dispose()


if __name__ == "__main__":
    results = run_test_scenarios()
