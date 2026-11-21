using Microsoft.PowerFx;
using Microsoft.PowerFx.Types;

namespace PowerFxReview;

/// <summary>Runs a formula against sample rows with the real Power Fx interpreter: what does it actually return?</summary>
public static class Evaluator
{
    public static async Task<string> RunAsync(string formula, ReviewContext ctx, string dataJson, IEnumerable<string>? screens = null)
        => Render(await EvalAsync(formula, ctx, dataJson, screens));

    public static async Task<FormulaValue> EvalAsync(string formula, ReviewContext ctx, string dataJson, IEnumerable<string>? screens = null)
    {
        var engine = new RecalcEngine();
        var values = ctx.BuildValues(dataJson);
        var scope = ctx.ToRecordType(screens ?? Array.Empty<string>());
        var check = engine.Check(formula, scope);
        if (!check.IsSuccess)
            throw new InvalidOperationException(string.Join("; ", check.Errors.Select(e => e.Message)));
        return await engine.EvalAsync(formula, CancellationToken.None, values);
    }

    /// <summary>Power Fx literal form of the result, e.g. a table of records or a number.</summary>
    public static string Render(FormulaValue v) => v switch
    {
        ErrorValue err => "Error: " + string.Join("; ", err.Errors.Select(e => e.Message)),
        _ => v.ToExpression(),
    };
}
