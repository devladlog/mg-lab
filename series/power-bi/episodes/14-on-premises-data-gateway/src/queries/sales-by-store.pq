let
    Source = Sql.Database("10.50.0.30", "ContosoBikesDW", [CreateNavigationProperties = false]),
    FactSales = Source{[Schema = "dbo", Item = "FactSales"]}[Data],
    DimStore = Source{[Schema = "dbo", Item = "DimStore"]}[Data],
    Joined = Table.NestedJoin(FactSales, {"StoreKey"}, DimStore, {"StoreKey"}, "StoreRow", JoinKind.Inner),
    Expanded = Table.ExpandTableColumn(Joined, "StoreRow", {"Store"}, {"Store"}),
    Grouped = Table.Group(
        Expanded,
        {"Store"},
        {
            {"Sales Amount", each List.Sum([LineAmount]), type number},
            {"Order Lines", each Table.RowCount(_), Int64.Type}
        }
    )
in
    Grouped
