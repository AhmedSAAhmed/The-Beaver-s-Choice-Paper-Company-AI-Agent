# Industry Best Practices

## Transparent customer-facing outputs

Customer responses pass through `customer_responses.py`, a dedicated presentation boundary. Internal database records and agent context remain separate from the JSON returned to a customer.

A customer quote includes all transaction-relevant information:

- quote ID, request date, expiration date, and quote status;
- each canonical product name and requested quantity;
- available and backordered quantities;
- unit price, discount percentage, and line total;
- supplier estimate when stock is unavailable;
- total quote price;
- a pricing rationale and an availability rationale for every line; and
- an overall explanation of whether the quote can be accepted immediately.

When a sale is confirmed, the response includes the order ID, quote ID, total, estimated dispatch date, and an explanation that acceptance, quote validity, and final stock were verified. Rejections explain what the customer can act on, such as an expired quote, missing quote ID, or insufficient stock.

## Information protection

The public quote serializer deliberately excludes `historical_examples`. Those internal records may contain earlier customer request text and quote explanations and are only used as agent context.

The fulfillment serializer maps low-level validation states such as `invalid_quote_data` to a neutral customer message. It does not expose database errors, stack traces, SQL, internal exception text, profit margins, purchasing costs, or unrelated customer information.

Company financial reports and cash-balance tools require the caller-supplied `allow_financial_report` flag. The orchestration model cannot grant this permission. An unauthorized request receives a short explanation without any financial values.

The test dataset itself contains business-role descriptions but no customer names, addresses, email addresses, telephone numbers, or payment information. The system does not add any new PII to its responses.

## Readability and modularity

The implementation uses the following conventions:

| Area | Convention |
| --- | --- |
| Functions and variables | Descriptive `snake_case` names |
| Pydantic models and dependency containers | `PascalCase` names |
| Public response logic | Isolated in `customer_responses.py` |
| Database and business workflows | Named functions with focused responsibilities |
| Agent tools | Small decorated functions that delegate to deterministic helpers |
| High-risk writes | Separate authorization checks and deterministic transaction functions |

Docstrings explain the purpose of public functions and non-obvious helpers. Comments are reserved for business rules and transaction guarantees, such as why a final stock check occurs inside the SQLite write transaction. Imports are consolidated at the top of the main module, and duplicate or unused imports have been removed.

## Automated checks

The tests verify that:

- public quotes include totals, dates, discount explanations, and stock explanations;
- historical customer requests and internal quote explanations are absent;
- internal validation status names and diagnostic details are not exposed;
- financial reports are unavailable without explicit authorization;
- every required starter helper remains attached to a registered agent tool; and
- the complete evaluation dataset continues to meet the fulfillment and cash-change thresholds.
