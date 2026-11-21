using Kusto.Language;
using Kusto.Language.Symbols;

// Columns used from EmailEvents (Microsoft Defender XDR advanced hunting schema, learn.microsoft.com):
// https://learn.microsoft.com/defender-xdr/advanced-hunting-emailevents-table
var emailEvents = new TableSymbol("EmailEvents",
    "(Timestamp:datetime, NetworkMessageId:string, SenderFromAddress:string, RecipientEmailAddress:string, Subject:string, " +
    "EmailDirection:string, DeliveryAction:string, DeliveryLocation:string, ThreatTypes:string, DetectionMethods:string, " +
    "LatestDeliveryAction:string, LatestDeliveryLocation:string, AttachmentCount:int, UrlCount:int)");
var globals = GlobalState.Default.WithDatabase(new DatabaseSymbol("hunting", emailEvents));

if (args.Length == 0) { Console.Error.WriteLine("usage: KqlCheck <file.kql> [more.kql ...]"); return 2; }
var failed = false;
foreach (var path in args)
{
    var code = KustoCode.ParseAndAnalyze(File.ReadAllText(path), globals);
    var errors = code.GetDiagnostics().Where(d => d.Severity == "Error").ToList();
    foreach (var d in errors) Console.WriteLine($"{path}: {d.Code} {d.Message} (at {d.Start})");
    if (errors.Count == 0) Console.WriteLine($"{path}: OK ({code.ResultType?.Name ?? "?"})");
    failed |= errors.Count > 0;
}
return failed ? 1 : 0;
