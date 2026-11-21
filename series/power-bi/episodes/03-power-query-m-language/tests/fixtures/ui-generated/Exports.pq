let
    Source = Folder.Files("C:\Users\AlexDemo\Downloads\exports"),
    #"Invoke Custom Function1" = Table.AddColumn(Source, "Transform File", each #"Transform File"([Content])),
    #"Expanded Table Column1" = Table.ExpandTableColumn(#"Invoke Custom Function1", "Transform File", {"OrderNumber", "LineNumber", "OrderDate", "Quantity", "UnitPrice"}),
    #"Changed Type" = Table.TransformColumnTypes(#"Expanded Table Column1",{{"OrderDate", type date}, {"Quantity", Int64.Type}, {"UnitPrice", type number}}),
    #"Sorted Rows" = Table.Sort(#"Changed Type",{{"Name", Order.Descending}}),
    #"Removed Duplicates" = Table.Distinct(#"Sorted Rows", {"OrderNumber", "LineNumber"})
in
    #"Removed Duplicates"
