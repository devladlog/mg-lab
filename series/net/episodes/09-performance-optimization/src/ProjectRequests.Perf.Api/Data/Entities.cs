namespace ProjectRequests.Perf.Api.Data;

public enum Priority { Standard, High }

public enum RequestStatus { Submitted, Approved, Rejected }

public sealed class Department
{
    public int Id { get; set; }
    public string Code { get; set; } = "";     // "FIN", "IT", "OPS"
    public string Name { get; set; } = "";
}

public sealed class Requester
{
    public int Id { get; set; }
    public string Name { get; set; } = "";
    public string Email { get; set; } = "";
}

public sealed class ProjectRequest
{
    public int Id { get; set; }
    public string Title { get; set; } = "";
    public decimal Budget { get; set; }
    public Priority Priority { get; set; }
    public RequestStatus Status { get; set; }
    public DateTime CreatedAtUtc { get; set; }

    public int DepartmentId { get; set; }
    public Department Department { get; set; } = null!;
    public int RequesterId { get; set; }
    public Requester Requester { get; set; } = null!;
}
