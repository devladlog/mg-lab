// TsqlParse: parse .sql files with Microsoft's T-SQL parser (ScriptDom, SQL Server 2022 grammar = TSql160Parser)
// and print one JSON document describing them. The Python tests use it to check the scripts that can't be
// executed locally (procedures, functions, security DDL): syntax first, then structure (parameters, SET options,
// TRY/CATCH, THROW, which built-in functions a module calls, GRANT targets...).
//
//   dotnet run -c Release -- file1.sql file2.sql ...      (or the built dll: dotnet bin/Release/net10.0/TsqlParse.dll ...)
//
// Exit code 0 when every file parses, 1 when any file has a syntax error.
using System.Text.Json;
using Microsoft.SqlServer.TransactSql.ScriptDom;

var files = new List<object>();
var anyError = false;

foreach (var path in args)
{
    var text = File.ReadAllText(path);
    var parser = new TSql160Parser(initialQuotedIdentifiers: true);
    var fragment = parser.Parse(new StringReader(text), out IList<ParseError> errors);
    anyError |= errors.Count > 0;

    var batches = new List<object>();
    var modules = new List<object>();
    if (fragment is TSqlScript script)
    {
        foreach (var batch in script.Batches)
        {
            var statements = new List<object>();
            foreach (var st in batch.Statements)
            {
                statements.Add(new { type = st.GetType().Name, line = st.StartLine, text = Src.Text(text, st) });
                if (Module.Describe(text, st) is { } m) modules.Add(m);
            }
            batches.Add(new { statements });
        }
    }

    files.Add(new
    {
        file = Path.GetFileName(path),
        errors = errors.Select(e => new { line = e.Line, column = e.Column, number = e.Number, message = e.Message }),
        batches,
        modules,
    });
}

Console.WriteLine(JsonSerializer.Serialize(files, new JsonSerializerOptions { WriteIndented = true }));
return anyError ? 1 : 0;

static class Src
{
    public static string Text(string source, TSqlFragment f) =>
        f.StartOffset >= 0 && f.FragmentLength > 0 ? source.Substring(f.StartOffset, f.FragmentLength) : "";
}

static class Module
{
    static string Text(string source, TSqlFragment f) => Src.Text(source, f);

    public static object? Describe(string source, TSqlStatement st)
    {
        switch (st)
        {
            case ProcedureStatementBody p:      // CREATE / ALTER / CREATE OR ALTER PROCEDURE
                return new
                {
                    kind = "procedure",
                    name = Name(p.ProcedureReference.Name),
                    parameters = p.Parameters.Select(Param),
                    options = p.Options.Select(o => o.OptionKind.ToString()),
                    body = Body(source, p.StatementList),
                };
            case FunctionStatementBody f:       // CREATE / ALTER / CREATE OR ALTER FUNCTION
                var kind = f.ReturnType switch
                {
                    ScalarFunctionReturnType => "scalar function",
                    SelectFunctionReturnType => "inline table-valued function",
                    TableValuedFunctionReturnType => "multi-statement table-valued function",
                    _ => "function",
                };
                var returns = new List<string>();
                var visitor = new Walker();
                f.Accept(visitor);
                foreach (var r in visitor.Returns) if (r.Expression != null) returns.Add(Text(source, r.Expression));
                return new
                {
                    kind,
                    name = Name(f.Name),
                    parameters = f.Parameters.Select(Param),
                    options = f.Options.Select(o => o.OptionKind.ToString()),
                    returnType = f.ReturnType is ScalarFunctionReturnType s ? Text(source, s.DataType) : null,
                    returnExpressions = returns,
                    selectText = f.ReturnType is SelectFunctionReturnType sel ? Text(source, sel.SelectStatement) : null,
                    body = Body(source, f.StatementList, f),
                };
            default:
                return null;
        }
    }

    static object Param(ProcedureParameter p) => new
    {
        name = p.VariableName.Value,
        type = p.DataType is SqlDataTypeReference or UserDataTypeReference or XmlDataTypeReference
            ? Name(p.DataType.Name) + Args(p.DataType)
            : p.DataType?.GetType().Name,
        output = p.Modifier == ParameterModifier.Output,
        readOnly = p.Modifier == ParameterModifier.ReadOnly,
        hasDefault = p.Value != null,
    };

    static string Args(DataTypeReference t) =>
        t is ParameterizedDataTypeReference pt && pt.Parameters.Count > 0
            ? "(" + string.Join(",", pt.Parameters.Select(x => x.Value)) + ")"
            : "";

    static string Name(SchemaObjectName? n) =>
        n == null ? "" : string.Join(".", n.Identifiers.Select(i => i.Value));

    static object Body(string source, StatementList? list, TSqlFragment? whole = null)
    {
        var w = new Walker();
        (whole ?? (TSqlFragment?)list)?.Accept(w);
        return new
        {
            nodeTypes = w.Types.OrderBy(x => x),
            functionCalls = w.Calls.OrderBy(x => x),
            setOptions = w.SetOptions,
            procedureCalls = w.Execs.OrderBy(x => x),
            variables = w.Variables.Select(v => new { name = v.VariableName.Value, value = v.Value == null ? null : Text(source, v.Value) }),
            topLevel = list?.Statements.Select(s => s.GetType().Name) ?? Enumerable.Empty<string>(),
        };
    }
}

// Collects every node type, every built-in or user function call, SET options and EXEC targets.
sealed class Walker : TSqlFragmentVisitor
{
    public HashSet<string> Types { get; } = new();
    public HashSet<string> Calls { get; } = new(StringComparer.OrdinalIgnoreCase);
    public HashSet<string> Execs { get; } = new(StringComparer.OrdinalIgnoreCase);
    public List<string> SetOptions { get; } = new();
    public List<ReturnStatement> Returns { get; } = new();
    public List<DeclareVariableElement> Variables { get; } = new();

    public override void Visit(TSqlFragment node) => Types.Add(node.GetType().Name);

    public override void ExplicitVisit(FunctionCall node)
    {
        var target = node.CallTarget is MultiPartIdentifierCallTarget t
            ? string.Join(".", t.MultiPartIdentifier.Identifiers.Select(i => i.Value)) + "."
            : "";
        Calls.Add((target + node.FunctionName.Value).ToUpperInvariant());
        base.ExplicitVisit(node);
    }

    public override void ExplicitVisit(PredicateSetStatement node)
    {
        foreach (SetOptions flag in Enum.GetValues(typeof(SetOptions)))
            if (flag != 0 && node.Options.HasFlag(flag)) SetOptions.Add($"{flag}={(node.IsOn ? "ON" : "OFF")}");
        base.ExplicitVisit(node);
    }

    public override void ExplicitVisit(ExecutableProcedureReference node)
    {
        if (node.ProcedureReference?.ProcedureReference?.Name is { } n)
            Execs.Add(string.Join(".", n.Identifiers.Select(i => i.Value)));
        base.ExplicitVisit(node);
    }

    public override void ExplicitVisit(DeclareVariableElement node)
    {
        Variables.Add(node);
        base.ExplicitVisit(node);
    }

    public override void ExplicitVisit(ReturnStatement node)
    {
        Returns.Add(node);
        base.ExplicitVisit(node);
    }
}
