using ExpenseClaims.Api.Claims;
using ExpenseClaims.Api.Infrastructure;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.RateLimiting;

namespace ExpenseClaims.Api.Controllers;

[ApiController]                                  // automatic 400s, binding inference, problem details for 4xx
[Route("api/claims")]
[Authorize]                                      // every action needs a valid bearer token
[ProducesResponseType(StatusCodes.Status401Unauthorized)]   // careful: with this, the inferred 200s vanished from OpenAPI
public sealed class ClaimsController(ClaimWorkflow workflow) : ControllerBase
{
    /// <summary>Employees see their own claims; approvers see everyone's.</summary>
    [HttpGet]
    [ProducesResponseType<IReadOnlyList<ExpenseClaim>>(StatusCodes.Status200OK)]
    public ActionResult<IReadOnlyList<ExpenseClaim>> List([FromQuery] ClaimStatus? status)
    {
        var owner = User.IsInRole(CurrentUser.ApproverRole) ? null : CurrentUser.Id(User);
        return Ok(workflow.List(owner, status));
    }

    [HttpGet("{id:int}")]
    [ProducesResponseType<ExpenseClaim>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status403Forbidden)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public ActionResult<ExpenseClaim> Get(int id)
    {
        var claim = workflow.Find(id);
        if (claim is null)
            return NotFound();                   // [ApiController] turns this into a 404 problem details

        if (claim.SubmittedBy != CurrentUser.Id(User) && !User.IsInRole(CurrentUser.ApproverRole))
            return Forbid();

        return claim;
    }

    [HttpPost]
    [EnableRateLimiting("submit")]               // per-user fixed window, 429 when exceeded
    [ProducesResponseType<ExpenseClaim>(StatusCodes.Status201Created)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status429TooManyRequests)]
    public ActionResult<ExpenseClaim> Submit(SubmitClaimRequest request)   // [FromBody] inferred
    {
        var claim = workflow.Submit(request, CurrentUser.Id(User));
        return CreatedAtAction(nameof(Get), new { id = claim.Id }, claim);
    }

    [HttpPost("{id:int}/approve")]
    [Authorize(Policy = "Approver")]             // needs the Claims.Approve app role
    [ProducesResponseType<ExpenseClaim>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status403Forbidden)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    [ProducesResponseType(StatusCodes.Status409Conflict)]
    public ActionResult<ExpenseClaim> Approve(int id) =>
        workflow.Approve(id, CurrentUser.Id(User));   // domain exceptions -> DomainExceptionHandler
}
