"""Safe, explainable serializers for customer-facing workflow results.

This module is intentionally separate from database and agent logic. It is the
single boundary that decides which fields may leave the internal system.
"""

import json
from decimal import Decimal
from typing import Any, Mapping


def _money(value: Any) -> str:
    """Format a numeric value as a two-decimal currency amount."""
    return f"{Decimal(str(value)):.2f}"


def customer_quote_response(quote: Any) -> str:
    """Return a complete quote without internal history or customer data."""
    public_lines = []

    for line in quote.lines:
        discount = int(line.discount_percent)
        pricing_rationale = (
            f"A {discount}% bulk discount was applied to this line."
            if discount
            else "The standard catalog unit price applies to this line."
        )

        if line.backordered:
            availability_rationale = (
                f"{line.available} units are currently available and "
                f"{line.backordered} require restocking."
            )
            if line.supplier_eta:
                availability_rationale += (
                    f" Estimated supplier availability is {line.supplier_eta}."
                )
        else:
            availability_rationale = (
                f"All {line.quantity} requested units are currently available."
            )

        public_lines.append({
            "item_name": line.item_name,
            "quantity": int(line.quantity),
            "available": int(line.available),
            "backordered": int(line.backordered),
            "unit_price": _money(line.unit_price),
            "discount_percent": discount,
            "line_total": _money(line.line_total),
            "supplier_eta": line.supplier_eta,
            "pricing_rationale": pricing_rationale,
            "availability_rationale": availability_rationale,
        })

    if quote.status == "ready":
        outcome_reason = (
            "All quoted items are currently available. "
            "The quote may be accepted before its expiration date."
        )
    else:
        outcome_reason = (
            "The order cannot be fulfilled immediately because at least one "
            "item requires restocking. Supplier estimates are shown per line."
        )

    return json.dumps(
        {
            "quote_id": quote.quote_id,
            "request_date": quote.request_date,
            "expires_on": quote.expires_on,
            "status": quote.status,
            "lines": public_lines,
            "total": _money(quote.total),
            "outcome_reason": outcome_reason,
        },
        indent=2,
    )


def customer_fulfillment_response(result: Mapping[str, Any]) -> str:
    """Translate an internal fulfillment result into a safe explanation."""
    status = str(result.get("status") or "unable_to_process")

    if status == "confirmed":
        payload = {
            "status": "confirmed",
            "order_id": result.get("order_id"),
            "quote_id": result.get("quote_id"),
            "total": _money(result.get("total", 0)),
            "estimated_dispatch_date": result.get("estimated_dispatch_date"),
            "reason": (
                "The quote was explicitly accepted, remained valid, and all "
                "items passed the final stock check."
            ),
        }
    elif status == "already_confirmed":
        payload = {
            "status": "already_confirmed",
            "order_id": result.get("order_id"),
            "quote_id": result.get("quote_id"),
            "total": _money(result.get("total", 0)),
            "estimated_dispatch_date": result.get("estimated_dispatch_date"),
            "reason": "This quote was already accepted; no duplicate sale was created.",
        }
    elif status == "insufficient_stock":
        payload = {
            "status": "not_fulfilled",
            "item_name": result.get("item_name"),
            "requested": result.get("required"),
            "available": result.get("available"),
            "reason": (
                "The order was not completed because the final stock check "
                "found insufficient inventory."
            ),
        }
    else:
        reasons = {
            "missing_quote_id": "A quote ID is required to accept an order.",
            "quote_not_found": "The supplied quote ID could not be found.",
            "quote_not_ready": (
                "This quote cannot be accepted because one or more items "
                "still require restocking."
            ),
            "order_date_before_quote": (
                "The order date cannot be earlier than the quote date."
            ),
            "quote_expired": (
                "This quote has expired. Please request a new quote."
            ),
        }
        payload = {
            "status": "not_fulfilled",
            "reason": reasons.get(
                status,
                "The order could not be completed. Please request assistance.",
            ),
        }

    return json.dumps(payload, indent=2)


def customer_message(status: str, reason: str) -> str:
    """Build a consistent customer-safe status response."""
    return json.dumps({"status": status, "reason": reason}, indent=2)
