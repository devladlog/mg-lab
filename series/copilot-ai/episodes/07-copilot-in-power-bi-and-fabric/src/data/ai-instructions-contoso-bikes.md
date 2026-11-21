Metrics
- "Sales" or "revenue" without another qualifier means [Sales Amount]: revenue before cost, one row per order line.
- "Margin" and "profit" mean [Margin]. "Margin percent" means [Margin %]. Do not average line-level percentages.
- "Orders" means [Orders] (distinct orders). "Units" means [Units].
- "Shipped orders" means [Orders Shipped].

Dates
- Use 'Date'[Date], which is the order date, for every time question unless the user asks about shipping.
- The data covers the calendar years 2024 and 2025. "Last year" means 2024 and "this year" means 2025, not the current date.

Ambiguity
- "Country" is ambiguous. 'Customer'[Country] is where the customer lives and 'Store'[Country] is where the sale was made. If the user does not say which one, ask.
- If "performance" could mean sales, margin or orders and the question does not say which, ask.

Terminology
- "Online" means 'Store'[Channel] is "Online". "Stores" means 'Store'[Channel] is "Store".
- "Top stores" means the three stores with the highest [Sales Amount].
