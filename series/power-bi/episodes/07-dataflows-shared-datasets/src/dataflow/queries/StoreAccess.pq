// Who manages which store (aliases only). The semantic model adds the sign-in domain and filters it with RLS.
let
    Files = SharePoint.Files(ExportSite, [ApiVersion = 15]),
    Mapping = Table.SelectRows(Files, each Text.EndsWith([Folder Path], "/security/") and [Name] = "store_access.csv"),
    Source = Csv.Document(Mapping{0}[Content], [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(Promoted, {{"UserAlias", type text}, {"StoreKey", Int64.Type}}, "en-US")
in
    Typed
