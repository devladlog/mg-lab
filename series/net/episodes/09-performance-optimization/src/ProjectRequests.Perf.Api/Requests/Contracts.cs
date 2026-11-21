using System.ComponentModel.DataAnnotations;
using ProjectRequests.Perf.Api.Data;

namespace ProjectRequests.Perf.Api.Requests;

public sealed record RequestDto(
    int Id, string Title, decimal Budget, string Department, string RequestedBy,
    Priority Priority, RequestStatus Status, DateTime CreatedAtUtc);

public sealed record PagedResult<T>(IReadOnlyList<T> Items, int Page, int PageSize, int Total);

public sealed record DepartmentSummary(string Code, int Count, decimal Budget);

public sealed record SummaryDto(IReadOnlyList<DepartmentSummary> Departments, int Total, decimal TotalBudget, DateTime ComputedAtUtc);

public sealed record CreateRequest(
    [property: Required, StringLength(100)] string Title,
    [property: Range(1, 10_000_000)] decimal Budget,
    [property: Required] string DepartmentCode,
    [property: Range(1, int.MaxValue)] int RequesterId);
