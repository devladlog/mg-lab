using Microsoft.AspNetCore.Components;
using Microsoft.Extensions.DependencyInjection;
using ProjectRequests.Web.Client.Pages;

namespace ProjectRequests.Web.Tests;

/// <summary>The WebAssembly page. bUnit renders it in-process; RendererInfo says where it "runs".</summary>
public sealed class NewRequestTests : BunitContext
{
    private readonly FakeRequestsApi _api = new();

    public NewRequestTests() => Services.AddSingleton<IRequestsApi>(_api);

    private IRenderedComponent<NewRequest> RenderInteractive()
    {
        SetRendererInfo(new RendererInfo("WebAssembly", isInteractive: true));
        return Render<NewRequest>();
    }

    private static void Fill(IRenderedComponent<NewRequest> cut, string budget, string? justification = null)
    {
        cut.Find("input[name='Model.Title']").Change("Laptop refresh");
        cut.Find("input[name='Model.RequestedBy']").Change("alex.demo@contoso.com");
        cut.Find("select").Change("FIN");
        cut.Find("#budget").Input(budget);
        if (justification is not null)
            cut.Find("textarea").Change(justification);
    }

    [Fact]
    public void While_prerendering_the_submit_button_is_disabled()
    {
        SetRendererInfo(new RendererInfo("Static", isInteractive: false));

        var cut = Render<NewRequest>();

        Assert.Contains("Rendered by: Static", cut.Find(".render-info").TextContent);
        Assert.True(cut.Find("button[type=submit]").HasAttribute("disabled"));
    }

    [Theory]
    [InlineData("49999.99", "Standard")]
    [InlineData("50000", "High")]
    public void Priority_preview_uses_the_shared_PriorityRules_while_typing(string budget, string expected)
    {
        var cut = RenderInteractive();

        cut.Find("#budget").Input(budget);

        Assert.Contains($"Priority: {expected}", cut.Find("#preview").TextContent);
        Assert.Empty(_api.Created);                                           // nothing sent to the API
    }

    [Fact]
    public void Big_budget_without_justification_is_stopped_in_the_browser()
    {
        var cut = RenderInteractive();
        Fill(cut, "300000");

        cut.Find("form").Submit();

        Assert.Contains("A justification is required for budgets of 250,000 or more.",
            cut.Find(".validation-errors").TextContent);                      // IValidatableObject from Contracts
        Assert.Empty(_api.Created);
    }

    [Fact]
    public void Valid_request_is_posted_and_the_new_id_is_shown()
    {
        var cut = RenderInteractive();
        Fill(cut, "75000");

        cut.Find("form").Submit();

        var sent = Assert.Single(_api.Created);
        Assert.Equal(75_000m, sent.Budget);
        Assert.Equal("FIN", sent.DepartmentCode);
        cut.WaitForAssertion(() => Assert.Contains("Request #7 created · High priority.", cut.Find("#created").TextContent));
    }

    [Fact]
    public void Errors_from_the_API_are_shown_with_their_field()
    {
        _api.NextFailure = new ApiResult<RequestDto>(null, "One or more validation errors occurred.",
            new Dictionary<string, string[]> { ["DepartmentCode"] = ["Unknown department 'HR'."] });
        var cut = RenderInteractive();
        Fill(cut, "1000");

        cut.Find("form").Submit();

        cut.WaitForAssertion(() =>
            Assert.Contains("DepartmentCode: Unknown department 'HR'.", cut.Find("#api-error").TextContent));
    }

    [Fact]
    public void An_unreachable_API_is_a_message_not_a_crash()
    {
        _api.Unreachable = true;
        var cut = RenderInteractive();
        Fill(cut, "1000");

        cut.Find("form").Submit();

        cut.WaitForAssertion(() =>
            Assert.Contains("Could not reach the API: TypeError: Failed to fetch", cut.Find("#api-error").TextContent));
        Assert.False(cut.Find("button[type=submit]").HasAttribute("disabled"));   // can retry
    }
}
