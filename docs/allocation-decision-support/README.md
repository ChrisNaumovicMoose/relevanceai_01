# Allocation Decision Support — [PoC R02] Stock Availability

## Problem

The US Operations team's effort is mostly spent answering "who should get the
inventory?", not "do we have inventory?". The `[PoC R02] Stock Availability`
agent (Relevance AI, `agent_id: 87b3121e-02cb-4a44-ab61-6a1bc49925ec`) only
answered the second question — it validated SKU/customer resolution,
sellability, stock position, demand commitments, inbound supply, carton
rules/pricing, and (USA) 12-digit stock proof and launch/embargo gating, then
returned a release verdict based purely on physical stock.

The `allocation_export_xlsx_1` knowledge base (weekly Customer x SKU records
with Forecast Qty, Allocation Qty, Open Order Qty, On Hand Snapshot, Inbound
Flow Qty, Balance Left, Allocation Note) contains the customer-entitlement
layer needed to answer the first question: a customer can be under-served or
over-served relative to their allocation even when plenty of physical stock
exists.

## What changed

Added **FR-USA-012: Check 11-USA — Allocation Assessment** (USA only) to the
agent's validation pipeline, positioned after Stage 1 physical shippability
(FR-001 through FR-USA-011) and before final verdict aggregation (FR-009):

- Looks up the resolved Customer x SKU x Week-Start record in
  `allocation_export_xlsx_1` (linked to the agent as a searchable knowledge
  tool).
- Treats `Balance-Left` as the export's own authoritative remaining-allocation
  figure when `Allocation-Qty > 0` — it is not re-derived from
  `Allocation-Qty - Open-Order-Qty`, since the export nets in other
  consumption (e.g. shipped/invoiced quantity) that a naive re-derivation
  would miss, verified against live records (e.g. Meijer / 11603.AD0.0000,
  week 2026-07-27: Allocation 450, Open Orders 0, Balance Left 217 — not 450).
- When `Allocation-Qty = 0` (no entitlement on file for that customer/SKU/
  week), treats the line as `NOT_ALLOCATED` / unconstrained rather than
  applying `Balance-Left` as a ceiling.
- Escalates (does not hard-block) when the requested quantity exceeds
  `Balance-Left` — physical stock availability never overrides a customer's
  allocation entitlement, and excess above the balance requires Allocation
  team review.
- Escalates when the matched record's `Mapping-Status` is unresolved/unmapped
  or `Staleness-Days` exceeds 14, rather than silently assuming no
  constraint.

`FR-009` (final verdict) now synthesizes both stages: `RELEASE_ELIGIBLE`
requires physical sufficiency **and** (for USA) that the order is within
allocation or unconstrained. An allocation breach or unverifiable allocation
record escalates the final verdict even when every Stage 1 check passed.

The agent's `knowledge` field now includes `allocation_export_xlsx_1`
(`usage_type: tool`), and the output JSON/human-readable summary were
extended with an `fr_usa_012_allocation_assessment` block and an
`allocation_status` summary field.

## Status

Changes are saved to the agent's **draft** version only — not published/live.
Stage 1 was smoke-tested against the draft with a real order (Meijer,
`11603.AD0.0000`, qty 500, ship date 2026-07-27) and resolved SKU/stock
correctly; full end-to-end verification of FR-USA-012 requires either raising
the agent's `autonomy_limit` (currently 20, `ask-for-approval`) or approving
the in-app continuation prompt, since Stage 1's exploratory SQL alone can
exceed the limit before Stage 2 runs.

Next step: review the draft in the Relevance AI app and publish when ready.
