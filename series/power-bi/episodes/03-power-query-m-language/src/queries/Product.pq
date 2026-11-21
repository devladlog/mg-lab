let
    Members = fnDimension(SalesExport, "ProductCode", {"ProductName", "Subcategory", "Category", "Color"}, "ProductKey"),
    Result = Table.RenameColumns(Members, {{"ProductName", "Product"}})
in
    Result
