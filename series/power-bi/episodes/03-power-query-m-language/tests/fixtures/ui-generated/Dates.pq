let
    Source = Exports,
    OrderDates = Table.TransformColumns(Source, {{"OrderDate", each Date.FromText(_, [Format = "dd/MM/yyyy", Culture = "pt-PT"]), type date}}),
    WithMonth = Table.AddColumn(OrderDates, "Month", each Date.Month([OrderDate]), Int64.Type),
    Result = Table.SelectRows(WithMonth, each [Month] = Selected)
in
    Result
