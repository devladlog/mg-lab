using PurchaseRequests.Api.Data;
using PurchaseRequests.Api.Domain;
using PurchaseRequests.Api.Security;

namespace PurchaseRequests.Tests;

public class RulesAndGuardTests
{
    static readonly ApprovalPolicy Policy = new() { Currency = "EUR", FinanceThreshold = 5000m, MaxAmount = 50000m };
    static PurchaseRequest Req(decimal amount, string owner = Ids.Alex, RequestStatus status = RequestStatus.Pending) =>
        new() { Amount = amount, RequestedByOid = owner, Status = status };
    static readonly Caller Sam = new(Ids.Sam, "Sam Demo", IsApprover: true, IsFinanceApprover: false);
    static readonly Caller Jordan = new(Ids.Jordan, "Jordan Demo", IsApprover: true, IsFinanceApprover: true);

    [Fact]
    public void Exactly_the_threshold_does_not_need_finance() =>
        Assert.True(ApprovalRules.CanDecide(Req(5000m), Sam, DecisionOutcome.Approve, Policy).Allowed);

    [Fact]
    public void One_cent_above_the_threshold_needs_finance() =>
        Assert.Equal(403, ApprovalRules.CanDecide(Req(5000.01m), Sam, DecisionOutcome.Approve, Policy).StatusCode);

    [Fact]
    public void Finance_approver_still_cannot_approve_own_request() =>
        Assert.Equal(403, ApprovalRules.CanDecide(Req(100m, owner: Ids.Jordan), Jordan, DecisionOutcome.Approve, Policy).StatusCode);

    [Fact]
    public void Owner_comparison_ignores_guid_casing() =>
        Assert.False(ApprovalRules.CanDecide(Req(100m, owner: Ids.Sam.ToUpperInvariant()), Sam, DecisionOutcome.Reject, Policy).Allowed);

    [Fact]
    public void Decided_request_is_a_conflict_before_anything_else() =>
        Assert.Equal(409, ApprovalRules.CanDecide(Req(100m, status: RequestStatus.Rejected), Sam, DecisionOutcome.Approve, Policy).StatusCode);

    [Theory]
    [InlineData("Server=tcp:x.database.windows.net;Database=pr;Authentication=Active Directory Default")]
    [InlineData("Server=tcp:x.database.windows.net;Database=pr;Authentication=Active Directory Managed Identity;User Id=00000000-0000-0000-0000-000000000000")]
    public void Entra_connection_strings_are_accepted(string cs) => SqlConnectionGuard.Validate(cs, isDevelopment: false);

    [Theory]
    [InlineData("Server=tcp:x.database.windows.net;Database=pr;User ID=sa;Password=NotARealOne1!")]
    [InlineData("Server=tcp:x.database.windows.net;Database=pr;Pwd=x;Authentication=Active Directory Default")]
    [InlineData("Server=tcp:x.database.windows.net;Database=pr")]
    [InlineData("")]
    public void Passwords_or_missing_entra_auth_stop_the_app_at_startup(string cs) =>
        Assert.Throws<InvalidOperationException>(() => SqlConnectionGuard.Validate(cs, isDevelopment: false));

    [Theory]
    [InlineData("common")]
    [InlineData("contoso.onmicrosoft.com")]
    public void Tenant_must_be_a_guid(string tenant) =>
        Assert.Throws<InvalidOperationException>(() => new EntraOptions { TenantId = tenant, ClientId = Ids.ApiClient }.Validate());

    [Fact]
    public void Issuers_cover_v1_and_v2_for_one_tenant_only()
    {
        var o = new EntraOptions { TenantId = Ids.Tenant, ClientId = Ids.ApiClient };
        Assert.Equal([$"https://login.microsoftonline.com/{Ids.Tenant}/v2.0", $"https://sts.windows.net/{Ids.Tenant}/"], EntraJwt.ValidIssuers(o));
        Assert.Equal([Ids.ApiClient, $"api://{Ids.ApiClient}"], EntraJwt.ValidAudiences(o));
    }
}
