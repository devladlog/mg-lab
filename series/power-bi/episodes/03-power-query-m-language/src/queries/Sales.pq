let
    Source = SalesExport,
    JoinProduct = Table.NestedJoin(Source, {"ProductCode"}, Product, {"ProductCode"}, "P", JoinKind.LeftOuter),
    WithProduct = Table.ExpandTableColumn(JoinProduct, "P", {"ProductKey"}),
    JoinCustomer = Table.NestedJoin(WithProduct, {"CustomerCode"}, Customer, {"CustomerCode"}, "C", JoinKind.LeftOuter),
    WithCustomer = Table.ExpandTableColumn(JoinCustomer, "C", {"CustomerKey"}),
    Guests = Table.ReplaceValue(WithCustomer, null, -1, Replacer.ReplaceValue, {"CustomerKey"}),
    JoinStore = Table.NestedJoin(Guests, {"StoreName"}, Store, {"Store"}, "S", JoinKind.LeftOuter),
    WithStore = Table.ExpandTableColumn(JoinStore, "S", {"StoreKey"}),
    Result = Table.SelectColumns(WithStore, {"OrderNumber", "LineNumber", "OrderDate", "ShipDate",
        "CustomerKey", "ProductKey", "StoreKey", "Quantity", "UnitPrice", "UnitCost"}),
    Typed = Table.TransformColumnTypes(Result, {
        {"CustomerKey", Int64.Type}, {"ProductKey", Int64.Type}, {"StoreKey", Int64.Type}
    }, "en-US")
in
    Typed
