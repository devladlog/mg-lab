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
    Result
