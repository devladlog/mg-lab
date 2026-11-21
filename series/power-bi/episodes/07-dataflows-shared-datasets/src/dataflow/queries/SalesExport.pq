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
    Result
