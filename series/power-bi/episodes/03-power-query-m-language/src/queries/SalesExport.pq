// Staging query (not loaded): every monthly export in the folder, combined and de-duplicated.
let
    Files = Folder.Files(ExportFolder),
    CsvOnly = Table.SelectRows(Files, each Text.Lower([Extension]) = ".csv"),
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
