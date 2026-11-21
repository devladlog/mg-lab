USE [ContosoCopilot];
GO
EXECUTE sp_addextendedproperty
    @name = N'CONSTITUTION.md',
    @value = N'---
agentExecuteAsUser: GHCP_DB_User

---
## Database constitution: ContosoCopilot

This database holds fictional Contoso customers, orders, order lines and products.

### Coding standards
- Always use explicit column lists. Do not use SELECT *.
- Use schema-qualified object names (Sales.Orders, not Orders).
- Wrap multi-statement scripts in a transaction with TRY/CATCH error handling.

### Restricted operations
- Avoid queries that modify data unless the user explicitly asks for it.
- Do not generate TRUNCATE TABLE statements.
- Do not generate DROP statements without an existence check.

### Business rules
- Revenue is SUM(Quantity * UnitPrice) from Sales.OrderLines.
- Orders with Status = N''Cancelled'' never count as revenue.';
GO
