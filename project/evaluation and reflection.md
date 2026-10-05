# Evaluation and Reflection

## Evaluation method

The system was evaluated against all 20 rows in `quote_requests_sample.csv`, in chronological order. The evaluation starts with a fresh in-memory SQLite database and inventory seed `40`, which makes the test repeatable while retaining a mixture of available and unavailable products.

For each row, the harness records the original request and date, quote outcome, fulfillment outcome, explanation, cash before and after processing, cash change, inventory value, and the complete quote and fulfillment responses. A quote is fulfilled only when its deterministic status is `ready`. The evaluation then supplies an explicit simulated acceptance and calls the same atomic `finalize_sale()` workflow used by the sales path. A quote that requires a backorder, contains an ambiguous item or unit, or fails validation remains unfulfilled with a reason.

The submitted run uses `replay_existing_agent_outputs` mode. It reuses the orchestration and quotation outputs already generated for the full dataset, then recalculates prices and stock against a clean database and exercises fulfillment locally. This avoids sending the dataset to the configured external model endpoint during the final reproducibility run. The `evaluation_mode` column makes this limitation visible rather than presenting the run as a new live-model evaluation.

The complete row-level output is in `test_results.csv`.

## Evaluation results

| Measure | Result |
| --- | ---: |
| Dataset requests evaluated | 20 of 20 |
| Successfully fulfilled requests | 3 |
| Requests that changed cash | 3 |
| Unfulfilled requests | 17 |
| Backorder-required quotes | 7 |
| Requests without a valid quote | 9 |
| Other controlled rejection | 1 |
| Initial cash balance | $45,596.76 |
| Final cash balance | $45,812.79 |
| Total cash increase | $216.03 |
| Initial inventory value | $4,403.24 |
| Final inventory value | $4,168.74 |

Requests 4, 6, and 10 were fulfilled successfully. Their respective cash changes were $11.88, $71.40, and $132.75, totaling $216.03. This satisfies both rubric thresholds: at least three fulfilled quote requests and at least three requests that change the cash balance.

The system deliberately did not fulfill every request. Requests 8, 11, 13, 14, 16, 18, and 19 required more stock and were retained as `backorder_required`. Other requests were rejected or held for clarification because of unknown catalog names, an unspecified box conversion, a unit mismatch exposed during offline replay, or missing authorization. Each unfulfilled row has a non-empty explanation in the `reason` column.

### Strengths demonstrated by the results

The strongest result is safe state handling. Only `ready` quotes reached fulfillment, and every successful sale changed both the cash balance and inventory through one atomic workflow. Stock-constrained quotes did not oversell inventory merely to improve the success rate.

The output is also auditable. Every source request appears exactly once, source request IDs are preserved, before-and-after financial values are explicit, and failures are separated into quote and fulfillment statuses. This makes the rubric claims directly checkable from the CSV instead of relying on console output.

Finally, deterministic pricing and fulfillment produced internally consistent changes: the three confirmed sale totals sum to the reported $216.03 cash increase, while inventory value fell after the corresponding stock was sold.

## Architecture and decision-making reflection

The workflow diagram describes four agents, staying below the five-agent limit:

1. The orchestration agent classifies a request as inventory, reorder, quote, quote acceptance, report, or clarification. It extracts only routing fields and cannot authorize writes.
2. The inventory and procurement agent owns stock queries, supplier estimates, management-data reads, gated reorders, and explicitly authorized stock receipts.
3. The quotation agent extracts catalog products, quantities, and units. It can inspect catalog, stock, and historical quote context, but deterministic Python calculates prices, discounts, availability, and delivery estimates.
4. The sales transaction agent verifies explicit acceptance and the quote ID. The subsequent deterministic workflow rechecks quote state and inventory before committing the sale.

This division was chosen to separate language interpretation from business-critical calculations and database mutations. The orchestration agent delegates by intent; specialist agents return narrow structured outputs; and deterministic functions enforce price, stock, authorization, idempotency, and transaction rules. The design prevents a model-generated statement from becoming a sale or purchase order without a controlled workflow checking it.

The evaluation follows that architecture. Historical agent outputs represent the routing and extraction stages, `calculate_quote()` applies quotation policy against the evaluation database, and `finalize_sale()` performs the final validation and state changes. Backordered or ambiguous requests stop before mutation.

## Further improvements

1. Add a catalog alias and unit-normalization layer before quotation. It should map phrases such as “printer paper,” sizes such as “A3,” and per-unit products such as streamers or napkins to canonical catalog entries while retaining the customer's original unit. This would reduce avoidable clarification failures without weakening validation.

2. Implement a complete backorder lifecycle. An approved purchase order should progress from pending to received, record the supplier transaction, update available stock on the delivery date, recalculate the quote, and request customer acceptance again. This would convert some of the seven stock-constrained cases into later fulfillments while keeping pending stock unavailable.

3. Add a local structured evaluation model or checked-in extraction fixture. That would exercise the orchestrator, quotation agent, and sales acceptance agent on every test run without an external endpoint, while remaining deterministic and safe for automated grading.

4. Expand evaluation metrics beyond rubric counts. Useful additions include intent accuracy, catalog-match accuracy, quote extraction accuracy by line item, fulfillment latency, discount correctness, and categorized failure rates. These metrics would show whether improvements reduce the right kinds of errors rather than merely increasing sales.
