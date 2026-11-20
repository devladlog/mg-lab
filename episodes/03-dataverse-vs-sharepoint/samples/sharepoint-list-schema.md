# SharePoint list — Project Requests

| Column | Internal name | Type |
|---|---|---|
| Title | `Title` | Single line of text |
| Requester | `Requester` | Single line of text |
| Department | `Department` | Choice (Finance, HR, Operations, Sales, IT) |
| Budget | `Budget` | Currency (EUR) |
| Status | `RequestStatus` | Choice (New, In review, Approved, Rejected, Done) |
| Priority | `Priority` | Choice (Low, Medium, High) |
| Due Date | `DueDate` | Date only |

Tips for lists that grow: index the columns you filter on (Status, Due Date) **before** passing 5,000 items,
and build views that filter on those indexed columns.
