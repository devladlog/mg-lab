let
    Members = fnDimension(SalesExport, "StoreName", {"StoreCountry", "Channel"}, "StoreKey"),
    Result = Table.RenameColumns(Members, {{"StoreName", "Store"}, {"StoreCountry", "Country"}})
in
    Result
