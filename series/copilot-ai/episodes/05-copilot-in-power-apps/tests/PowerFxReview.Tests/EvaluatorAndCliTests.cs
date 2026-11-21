using Microsoft.PowerFx.Types;
using PowerFxReview;
using Xunit;

namespace PowerFxReview.Tests;

public class EvaluatorTests
{
    static async Task<FormulaValue> Eval(string formula) =>
        await Evaluator.EvalAsync(formula, Samples.Context(), Samples.Data);

    [Fact]
    public async Task Overdue_means_strictly_before_today()
    {
        // Sample rows: due today-5 and today-1 (open), today (open, NOT overdue), today+7, and one already returned.
        var v = await Eval("CountRows(Filter(Loans, IsBlank(ReturnedOn) && DueDate < Today()))");
        Assert.Equal(2.0, Convert.ToDouble(v.ToObject()));
    }

    [Fact]
    public async Task A_less_or_equal_variant_also_counts_the_loan_due_today()
    {
        var v = await Eval("CountRows(Filter(Loans, IsBlank(ReturnedOn) && DueDate <= Today()))");
        Assert.Equal(3.0, Convert.ToDouble(v.ToObject()));
    }

    [Fact]
    public async Task Concat_lists_the_borrowers()
    {
        var v = await Eval("Concat(Filter(Loans, IsBlank(ReturnedOn) && DueDate < Today()), Borrower, \", \")");
        Assert.Equal("Alex Demo, Sam Demo", v.ToObject());
    }

    [Fact]
    public async Task Control_values_come_from_the_data_file()
    {
        var data = """{ "Loans": [], "txtSearch": { "Text": "Sam" }, "galLoans": { "Selected": { "Borrower": "Sam Demo" } } }""";
        var v = await Evaluator.EvalAsync("txtSearch.Text & \"/\" & galLoans.Selected.Borrower", Samples.Context(), data);
        Assert.Equal("Sam/Sam Demo", v.ToObject());
    }

    [Fact]
    public async Task A_formula_with_errors_is_not_run()
    {
        await Assert.ThrowsAsync<InvalidOperationException>(() => Eval("CountRows(Loanz)"));
    }

    [Theory]
    [InlineData("today", 0)]
    [InlineData("today-5", -5)]
    [InlineData("today+7", 7)]
    public void Relative_dates(string text, int offset)
    {
        var today = new DateTime(2026, 11, 21);
        Assert.Equal(today.AddDays(offset), ReviewContext.ParseDate(text, today));
    }

    [Fact]
    public void Absolute_dates_parse()
        => Assert.Equal(new DateTime(2026, 12, 31), ReviewContext.ParseDate("2026-12-31"));

    [Fact]
    public void Unknown_type_in_the_context_file_is_reported()
        => Assert.Throws<FormatException>(() => ReviewContext.Parse("""{ "variables": { "x": "currency" } }"""));
}

public class CliTests
{
    static async Task<(int Code, string Out, string Err)> Run(params string[] args)
    {
        var o = new StringWriter(); var e = new StringWriter();
        int code = await Cli.RunAsync(args, o, e);
        return (code, o.ToString(), e.ToString());
    }

    static string Ctx => Path.Combine(Samples.Root, "context.json");

    [Fact]
    public async Task Review_of_the_sample_app_finds_the_planted_problems_and_exits_1()
    {
        var (code, output, _) = await Run("review", Samples.Src, "--context", Ctx);
        Assert.Equal(1, code);
        Assert.Contains("15 formulas: 5 clean, 4 with warnings, 5 partly checked, 3 with errors", output);
        Assert.Contains("PF001", output);
        Assert.Contains("PF002", output);
        Assert.Contains("PF003", output);
        Assert.Contains("PF004", output);
        Assert.Contains("PF005", output);
    }

    [Fact]
    public async Task Check_a_clean_formula_exits_0()
    {
        var (code, output, _) = await Run("check", "Upper(txtSearch.Text)", "--context", Ctx);
        Assert.Equal(0, code);
        Assert.Contains("OK", output);
    }

    [Fact]
    public async Task Json_output_is_parseable()
    {
        var (code, output, _) = await Run("check", "galLoans.Selected.Borrowr", "--context", Ctx, "--json");
        Assert.Equal(1, code);
        using var doc = System.Text.Json.JsonDocument.Parse(output);
        var first = doc.RootElement[0];
        Assert.Equal("error", first.GetProperty("status").GetString());
        Assert.Equal("PF001", first.GetProperty("findings")[0].GetProperty("Code").GetString());
    }

    [Fact]
    public async Task Run_prints_the_result_on_sample_data()
    {
        var (code, output, _) = await Run("run", "CountRows(Filter(Loans, IsBlank(ReturnedOn)))", "--context", Ctx,
            "--data", Path.Combine(Samples.Root, "sample-data.json"));
        Assert.Equal(0, code);
        Assert.Contains("4", output);
    }

    [Fact]
    public async Task Missing_context_is_a_usage_error()
    {
        var (code, _, err) = await Run("check", "1+1");
        Assert.Equal(2, code);
        Assert.Contains("--context is required", err);
    }

    [Fact]
    public async Task Review_works_on_an_unzipped_msapp_layout()
    {
        // An .msapp is a zip. Learn: the source is the *.pa.yaml files in its src folder; other files must not be used as source.
        var work = Path.Combine(Path.GetTempPath(), $"msapp-{Guid.NewGuid():N}");
        var zip = work + ".zip";
        try
        {
            Directory.CreateDirectory(work);
            using (var z = System.IO.Compression.ZipFile.Open(zip, System.IO.Compression.ZipArchiveMode.Create))
            {
                foreach (var f in Directory.GetFiles(Samples.Src, "*.pa.yaml"))
                    System.IO.Compression.ZipFileExtensions.CreateEntryFromFile(z, f, "src/" + Path.GetFileName(f));
                var manifest = z.CreateEntry("CanvasManifest.json");
                using (var w = new StreamWriter(manifest.Open())) w.Write("{}");
            }
            System.IO.Compression.ZipFile.ExtractToDirectory(zip, work);

            var (code, output, _) = await Run("review", work, "--context", Ctx);
            Assert.Equal(1, code);
            Assert.Contains("15 formulas", output);
        }
        finally { Directory.Delete(work, true); File.Delete(zip); }
    }

    [Fact]
    public async Task Invalid_yaml_is_reported_not_thrown()
    {
        var bad = Path.Combine(Path.GetTempPath(), $"bad-{Guid.NewGuid():N}.pa.yaml");
        File.WriteAllText(bad, "Screens:\n  S1:\n    Children:\n      - b:\n          Control: Button\n          Properties:\n            OnSelect: =Patch(T, X, {A: 1})\n");
        try
        {
            var (code, _, err) = await Run("review", bad, "--context", Ctx);
            Assert.Equal(2, code);
            Assert.StartsWith("error:", err);
        }
        finally { File.Delete(bad); }
    }
}
