using System.Globalization;
using System.Text.Json;
using Microsoft.PowerFx;
using Microsoft.PowerFx.Types;

namespace PowerFxReview;

/// <summary>
/// What a formula may refer to: Dataverse/SharePoint tables, controls, variables, enums.
/// Loaded from a small JSON file because the standalone Power Fx engine has no idea what is in the app.
/// </summary>
public sealed class ReviewContext
{
    public Dictionary<string, TableInfo> Tables { get; } = new(StringComparer.Ordinal);
    public Dictionary<string, FormulaType> Controls { get; } = new(StringComparer.Ordinal);
    public Dictionary<string, FormulaType> Variables { get; } = new(StringComparer.Ordinal);
    public Dictionary<string, string[]> Enums { get; } = new(StringComparer.Ordinal)
    {
        // Values taken from the Navigate and Notify pages on Microsoft Learn.
        ["ScreenTransition"] = new[] { "Cover", "CoverRight", "Fade", "None", "UnCover", "UnCoverRight" },
        ["NotificationType"] = new[] { "Error", "Information", "Success", "Warning" },
    };

    public sealed record TableInfo(RecordType Row, bool DataSource);

    public static ReviewContext Load(string path) => Parse(File.ReadAllText(path));

    public static ReviewContext Parse(string json)
    {
        var ctx = new ReviewContext();
        using var doc = JsonDocument.Parse(json, new JsonDocumentOptions { CommentHandling = JsonCommentHandling.Skip });
        var root = doc.RootElement;

        if (root.TryGetProperty("tables", out var tables))
            foreach (var t in tables.EnumerateObject())
            {
                var row = RecordType.Empty();
                foreach (var col in t.Value.GetProperty("columns").EnumerateObject())
                    row = row.Add(col.Name, ParseType(col.Value, ctx));
                bool ds = t.Value.TryGetProperty("datasource", out var d) && d.GetBoolean();
                ctx.Tables[t.Name] = new TableInfo(row, ds);
            }
        if (root.TryGetProperty("controls", out var controls))
            foreach (var c in controls.EnumerateObject())
                ctx.Controls[c.Name] = ParseType(c.Value, ctx);
        if (root.TryGetProperty("variables", out var vars))
            foreach (var v in vars.EnumerateObject())
                ctx.Variables[v.Name] = ParseType(v.Value, ctx);
        if (root.TryGetProperty("enums", out var enums))
            foreach (var e in enums.EnumerateObject())
                ctx.Enums[e.Name] = e.Value.EnumerateArray().Select(x => x.GetString()!).ToArray();
        return ctx;
    }

    /// <summary>"string" | "number" | "boolean" | "date" | "datetime" | {"record": "Table"} | {"table": "Table"} | {"fields": {...}}.</summary>
    internal static FormulaType ParseType(JsonElement el, ReviewContext ctx)
    {
        if (el.ValueKind == JsonValueKind.String)
        {
            return el.GetString()!.ToLowerInvariant() switch
            {
                "string" or "text" => FormulaType.String,
                "number" => FormulaType.Number,
                "boolean" or "bool" => FormulaType.Boolean,
                "date" => FormulaType.Date,
                "datetime" => FormulaType.DateTime,
                var other => throw new FormatException($"Unknown type '{other}' in the context file"),
            };
        }
        if (el.TryGetProperty("record", out var rec))
            return ctx.Tables[rec.GetString()!].Row;
        if (el.TryGetProperty("table", out var tab))
            return ctx.Tables[tab.GetString()!].Row.ToTable();
        if (el.TryGetProperty("fields", out var fields))
        {
            var r = RecordType.Empty();
            foreach (var f in fields.EnumerateObject()) r = r.Add(f.Name, ParseType(f.Value, ctx));
            return r;
        }
        throw new FormatException("A type is a string or an object with record, table or fields");
    }

    /// <summary>Everything a formula can name, as one record type: that is what Check() wants.</summary>
    public RecordType ToRecordType(IEnumerable<string> screenNames)
    {
        var rt = RecordType.Empty();
        foreach (var (name, info) in Tables) rt = rt.Add(name, info.Row.ToTable());
        foreach (var (name, type) in Controls) rt = rt.Add(name, type);
        foreach (var (name, type) in Variables) rt = rt.Add(name, type);
        foreach (var (name, values) in Enums)
        {
            var e = RecordType.Empty();
            foreach (var v in values) e = e.Add(v, FormulaType.String);
            rt = rt.Add(name, e);
        }
        // Screens are valid arguments of Navigate; give them an empty record type.
        foreach (var s in screenNames.Distinct())
            if (!Tables.ContainsKey(s) && !Controls.ContainsKey(s))
                rt = rt.Add(s, RecordType.Empty());
        return rt;
    }

    /// <summary>
    /// Sample rows for the run mode. Date values may be "2026-11-21" or "today-3" / "today+10", so a sample file never goes stale.
    /// </summary>
    public RecordValue BuildValues(string dataJson)
    {
        using var doc = JsonDocument.Parse(dataJson);
        var fields = new List<NamedValue>();
        foreach (var (name, info) in Tables)
        {
            var rows = new List<RecordValue>();
            if (doc.RootElement.TryGetProperty(name, out var arr))
                foreach (var item in arr.EnumerateArray())
                    rows.Add(BuildRecord(info.Row, item));
            fields.Add(new NamedValue(name, FormulaValue.NewTable(info.Row, rows)));
        }
        foreach (var (name, type) in Controls)
            if (doc.RootElement.TryGetProperty(name, out var c) && type is RecordType rt)
                fields.Add(new NamedValue(name, BuildRecord(rt, c)));
        foreach (var (name, type) in Variables)
            if (doc.RootElement.TryGetProperty(name, out var v))
                fields.Add(new NamedValue(name, BuildValue(type, v)));
        foreach (var (name, values) in Enums)
        {
            var e = RecordType.Empty();
            foreach (var v in values) e = e.Add(v, FormulaType.String);
            fields.Add(new NamedValue(name, FormulaValue.NewRecordFromFields(e, values.Select(v => new NamedValue(v, FormulaValue.New(v))))));
        }
        return FormulaValue.NewRecordFromFields(fields.ToArray());
    }

    static RecordValue BuildRecord(RecordType type, JsonElement item)
    {
        var fields = new List<NamedValue>();
        foreach (var f in type.GetFieldTypes())
        {
            FormulaValue val = item.TryGetProperty(f.Name, out var p) && p.ValueKind != JsonValueKind.Null
                ? BuildValue(f.Type, p)
                : FormulaValue.NewBlank(f.Type);
            fields.Add(new NamedValue(f.Name, val));
        }
        return FormulaValue.NewRecordFromFields(type, fields);
    }

    static FormulaValue BuildValue(FormulaType type, JsonElement p)
    {
        if (type is RecordType rt) return BuildRecord(rt, p);
        if (type == FormulaType.String) return FormulaValue.New(p.GetString() ?? "");
        if (type == FormulaType.Number) return FormulaValue.New(p.GetDouble());
        if (type == FormulaType.Boolean) return FormulaValue.New(p.GetBoolean());
        if (type == FormulaType.Date) return FormulaValue.NewDateOnly(ParseDate(p.GetString()!).Date);
        if (type == FormulaType.DateTime) return FormulaValue.New(ParseDate(p.GetString()!));
        throw new NotSupportedException($"Cannot build a sample value of type {type}");
    }

    public static DateTime ParseDate(string text, DateTime? today = null)
    {
        var t = today ?? DateTime.Today;
        text = text.Trim();
        if (text.StartsWith("today", StringComparison.OrdinalIgnoreCase))
        {
            var rest = text[5..].Trim();
            if (rest.Length == 0) return t;
            return t.AddDays(int.Parse(rest, CultureInfo.InvariantCulture));
        }
        return DateTime.Parse(text, CultureInfo.InvariantCulture, DateTimeStyles.AssumeLocal);
    }
}
