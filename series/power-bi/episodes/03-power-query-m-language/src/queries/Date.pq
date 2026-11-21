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
        #"Month Number" = Date.Month(d),
        Month = Date.ToText(d, [Format = "MMM", Culture = "en-US"]),
        #"Year Month" = Date.ToText(d, [Format = "yyyy-MM", Culture = "en-US"]),
        #"Year Month Number" = Date.Year(d) * 100 + Date.Month(d),
        #"Day of Week Number" = Date.DayOfWeek(d, Day.Monday) + 1,
        #"Day of Week" = Date.ToText(d, [Format = "ddd", Culture = "en-US"])
    ]),
    Calendar = Table.FromRecords(Rows),
    Typed = Table.TransformColumnTypes(Calendar, {
        {"Date", type date}, {"Year", Int64.Type}, {"Quarter", type text}, {"Month Number", Int64.Type},
        {"Month", type text}, {"Year Month", type text}, {"Year Month Number", Int64.Type},
        {"Day of Week Number", Int64.Type}, {"Day of Week", type text}
    }, "en-US")
in
    Typed
