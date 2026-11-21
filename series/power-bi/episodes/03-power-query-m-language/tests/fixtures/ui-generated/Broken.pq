let
    Source = Exports,
    Big = Table.SelectRows(Source, each [Quantity] > )
in
    Big
