# ERP business rules (reference only — RAG indexes business_logic.pdf, not this file)

Use `scripts/generate_knowledge_pdf.py` to build a starter PDF, or replace `app/knowledge/business_logic.pdf` directly.

## Credit and customers

- Credit limit comparisons use INR. One lakh = 100,000 (e.g. 5 lakhs = 500,000).
- High credit customers: filter `customers.credit_limit` with the threshold from the question.
- Outstanding balance questions use `customers.outstanding_balance`; do not confuse with credit limit.

## Sales and revenue

- Default revenue uses `SUM(sales_orders.total_amount)` (tax included).
- Use `SUM(sales_orders.subtotal)` only when the user asks for pre-tax subtotal.
- Exclude `sales_orders.status` in ('Draft', 'Cancelled') unless the user asks for all orders.
- Line-level revenue ranking: `SUM(order_items.line_total)` grouped by product.

## Products and inventory

- SKU lookups filter `products.sku` and join `inventory` on `product_id`.
- Available stock per warehouse: `stock_on_hand - allocated_stock`.
- Low stock: available quantity `<= reorder_level`.
- Fast-moving / top selling: rank by `SUM(order_items.quantity)` as units_sold in the current year.

## Multi-step questions

- Credit/customer questions and SKU/inventory questions are separate targets.
- Do not join `customers` to `inventory` unless the user explicitly asks for a cross-domain metric.

## Count and listing queries

- "How many warehouses" → `COUNT(DISTINCT inventory.warehouse_name)`.
- Use aggregates for KPI questions instead of returning large raw row sets.
