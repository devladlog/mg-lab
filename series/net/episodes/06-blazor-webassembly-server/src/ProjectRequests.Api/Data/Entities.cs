namespace ProjectRequests.Api.Data;

/// <summary>Reference data, seeded by the migrations (HasData).</summary>
public sealed class Department
{
    public int Id { get; set; }
    public string Code { get; set; } = "";          // "FIN", "IT", "OPS" - always upper case
    public string Name { get; set; } = "";
    public List<ProjectRequest> Requests { get; } = [];
}

/// <summary>
/// The entity EF Core maps to the ProjectRequests table. The API never returns it directly:
/// endpoints project to <see cref="Requests.RequestDto"/>.
/// </summary>
public sealed class ProjectRequest
{
    public int Id { get; set; }
    public string Title { get; set; } = "";
    public decimal Budget { get; set; }
    public string RequestedBy { get; set; } = "";
    public string? Justification { get; set; }
    public Priority Priority { get; set; }
    public RequestStatus Status { get; set; }

    // DateTime (UTC), not DateTimeOffset: SQLite can't compare or order DateTimeOffset in SQL.
    public DateTime CreatedAtUtc { get; set; }
    public string? DecidedBy { get; set; }
    public DateTime? DecidedAtUtc { get; set; }

    public int DepartmentId { get; set; }
    public Department Department { get; set; } = null!;

    /// <summary>
    /// Application-managed concurrency token: works on SQLite and SQL Server alike.
    /// Every write must assign a new value (see <see cref="Touch"/>).
    /// </summary>
    public Guid Version { get; set; }

    public void Touch() => Version = Guid.NewGuid();
}
