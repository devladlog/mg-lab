## What and why
Adds `POST /orders/{id}/cancel`. Support needs to cancel an order from the admin screen without deleting it, so the order keeps its history.
Orders get a `Status` (`open` by default, `cancelled` after the call).

## How to verify
`dotnet test` (new: `CancelTests`). By hand: create an order with `POST /orders`, then `POST /orders/<id>/cancel` and read it back with `GET /orders/<id>`: `status` is `cancelled`.

## Where to look
`Program.cs` (the new endpoint, 8 lines) and the `Status` property in `Orders.cs`. The test file is new and short.

## Risk and rollback
Additive: a new column with a default and a new route, nothing existing changes. The demo app creates its schema with `EnsureCreated`, so an existing database file would not get the column; the deployed container's data resets on every deploy (episode 5). Rollback: revert the commit.

## Out of scope
Listing or filtering by status, un-cancelling, notifying the customer.
