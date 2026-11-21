let
    Members = fnDimension(SalesExport, "CustomerCode", {"CustomerName", "CustomerCity", "CustomerCountry"}, "CustomerKey"),
    Renamed = Table.RenameColumns(Members, {{"CustomerName", "Customer"}, {"CustomerCity", "City"}, {"CustomerCountry", "Country"}}),
    // Guest orders have no customer: give them an explicit member instead of a blank row in the visuals.
    Result = Table.InsertRows(Renamed, 0, {
        [CustomerKey = -1, CustomerCode = "", Customer = "Unknown customer", City = "Unknown", Country = "Unknown"]
    })
in
    Result
