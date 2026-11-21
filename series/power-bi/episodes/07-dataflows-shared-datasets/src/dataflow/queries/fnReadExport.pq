// One monthly ERP export -> typed table. Semicolons, decimal comma, day/month/year dates, TOTAL footer.
(file as binary) as table =>
let
    Source = Csv.Document(file, [Delimiter = ";", Columns = 19, Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    NoTotals = Table.SelectRows(Promoted, each [OrderNumber] <> "TOTAL"),
    Cleaned = Table.TransformColumns(NoTotals, {
        {"ProductCode", each Text.Upper(Text.Trim(_)), type text},
        {"CustomerCode", each if Text.Trim(_) = "" then null else Text.Trim(_), type nullable text},
        // "/" in a format string is the culture's date separator: quote it to mean a literal slash
        {"OrderDate", each Date.FromText(_, [Format = "dd'/'MM'/'yyyy", Culture = "pt-PT"]), type date},
        {"ShipDate", each Date.FromText(_, [Format = "dd'/'MM'/'yyyy", Culture = "pt-PT"]), type date}
    }),
    TextColumns = {"OrderNumber", "CustomerName", "CustomerCity", "CustomerCountry", "StoreName",
        "StoreCountry", "Channel", "ProductName", "Subcategory", "Category", "Color"},
    Typed = Table.TransformColumnTypes(
        Cleaned,
        List.Transform(TextColumns, each {_, type text})
            & {{"LineNumber", Int64.Type}, {"Quantity", Int64.Type}, {"UnitPrice", Currency.Type}, {"UnitCost", Currency.Type}},
        "pt-PT"
    )
in
    Typed
