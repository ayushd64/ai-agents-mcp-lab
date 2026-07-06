# Data dictionary — sales data

## Columns
- date: the transaction date, format YYYY-MM-DD.
- region: the sales region. One of: North, South, East, West.
- product: the product sold. One of: Widget, Gadget.
- revenue: total sales revenue for that row, in US dollars (USD), excluding tax.
- units: the number of individual items sold in that transaction.

## Definitions and business rules
- Quarters: Q1 = January–March, Q2 = April–June, Q3 = July–September, Q4 = October–December.
- Growth between two periods = (later value − earlier value) / earlier value, as a percentage.
- "Best" or "top" region means the region with the highest total revenue, unless the user asks about units.
- Revenue per unit = revenue / units.
- A "unit" is one physical item sold.

