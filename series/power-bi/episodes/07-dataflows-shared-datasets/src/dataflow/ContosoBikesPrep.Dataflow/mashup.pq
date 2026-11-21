section Section1;

shared ExportSite =
"https://contoso.sharepoint.com/sites/ContosoBikesData" meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true];

shared fnReadExport =
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
    Typed;

shared fnDimension =
// Distinct members of a business key + attributes, sorted, with a surrogate key starting at 1.
(source as table, businessKey as text, attributes as list, keyName as text) as table =>
let
    Columns = Table.SelectColumns(source, {businessKey} & attributes),
    Known = Table.SelectRows(Columns, each Record.Field(_, businessKey) <> null),
    Members = Table.Distinct(Known),
    Sorted = Table.Sort(Members, {{businessKey, Order.Ascending}}),
    Keyed = Table.AddIndexColumn(Sorted, keyName, 1, 1, Int64.Type),
    Result = Table.ReorderColumns(Keyed, {keyName, businessKey} & attributes)
in
    Result;

shared SalesExport =
// Staging query (not loaded): every monthly export in the site's exports folder, combined and de-duplicated.
// Episode 3 read the same files from a local folder (Folder.Files); in the service they live in SharePoint.
let
    Files = SharePoint.Files(ExportSite, [ApiVersion = 15]),
    InFolder = Table.SelectRows(Files, each Text.EndsWith([Folder Path], "/exports/")),
    CsvOnly = Table.SelectRows(InFolder, each Text.Lower([Extension]) = ".csv"),
    Read = Table.AddColumn(CsvOnly, "Data",
        (file) => Table.AddColumn(fnReadExport(file[Content]), "SourceFile", each file[Name], type text)),
    Combined = Table.Combine(Read[Data]),
    // Each file re-exports the last days of the previous month with corrections: the newest file wins.
    Newest = Table.Sort(Combined, {{"SourceFile", Order.Descending}}),
    Buffered = Table.Buffer(Newest),
    Deduped = Table.Distinct(Buffered, {"OrderNumber", "LineNumber"}),
    Result = Table.RemoveColumns(Deduped, {"SourceFile"})
in
    Result;

shared Product =
let
    Members = fnDimension(SalesExport, "ProductCode", {"ProductName", "Subcategory", "Category", "Color"}, "ProductKey"),
    Result = Table.RenameColumns(Members, {{"ProductName", "Product"}})
in
    Result;

shared Customer =
let
    Members = fnDimension(SalesExport, "CustomerCode", {"CustomerName", "CustomerCity", "CustomerCountry"}, "CustomerKey"),
    Renamed = Table.RenameColumns(Members, {{"CustomerName", "Customer"}, {"CustomerCity", "City"}, {"CustomerCountry", "Country"}}),
    // Guest orders have no customer: give them an explicit member instead of a blank row in the visuals.
    Result = Table.InsertRows(Renamed, 0, {
        [CustomerKey = -1, CustomerCode = "", Customer = "Unknown customer", City = "Unknown", Country = "Unknown"]
    })
in
    Result;

shared Store =
let
    Members = fnDimension(SalesExport, "StoreName", {"StoreCountry", "Channel"}, "StoreKey"),
    Result = Table.RenameColumns(Members, {{"StoreName", "Store"}, {"StoreCountry", "Country"}})
in
    Result;

shared Date =
// Column names are the dataflow contract's (letters and digits only); the model shows them with spaces.
// Full calendar years covering every order date and ship date (ship dates spill into the next year).
let
    AllDates = SalesExport[OrderDate] & SalesExport[ShipDate],
    FirstDay = #date(Date.Year(List.Min(AllDates)), 1, 1),
    LastDay = #date(Date.Year(List.Max(AllDates)), 12, 31),
    Days = List.Dates(FirstDay, Duration.Days(LastDay - FirstDay) + 1, #duration(1, 0, 0, 0)),
    Rows = List.Transform(Days, (d) => [
        Date = d,
        Year = Date.Year(d),
        Quarter = "Q" & Text.From(Date.QuarterOfYear(d)),
        MonthNumber = Date.Month(d),
        Month = Date.ToText(d, [Format = "MMM", Culture = "en-US"]),
        YearMonth = Date.ToText(d, [Format = "yyyy-MM", Culture = "en-US"]),
        YearMonthNumber = Date.Year(d) * 100 + Date.Month(d),
        DayOfWeekNumber = Date.DayOfWeek(d, Day.Monday) + 1,
        DayOfWeek = Date.ToText(d, [Format = "ddd", Culture = "en-US"])
    ]),
    Calendar = Table.FromRecords(Rows),
    Typed = Table.TransformColumnTypes(Calendar, {
        {"Date", type date}, {"Year", Int64.Type}, {"Quarter", type text}, {"MonthNumber", Int64.Type},
        {"Month", type text}, {"YearMonth", type text}, {"YearMonthNumber", Int64.Type},
        {"DayOfWeekNumber", Int64.Type}, {"DayOfWeek", type text}
    }, "en-US")
in
    Typed;

shared Sales =
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
    Typed;

shared StoreAccess =
// Who manages which store (aliases only). The semantic model adds the sign-in domain and filters it with RLS.
let
    Files = SharePoint.Files(ExportSite, [ApiVersion = 15]),
    Mapping = Table.SelectRows(Files, each Text.EndsWith([Folder Path], "/security/") and [Name] = "store_access.csv"),
    Source = Csv.Document(Mapping{0}[Content], [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(Promoted, {{"UserAlias", type text}, {"StoreKey", Int64.Type}}, "en-US")
in
    Typed;
