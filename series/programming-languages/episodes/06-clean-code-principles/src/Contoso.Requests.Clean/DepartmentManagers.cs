using System.Collections.Frozen;
using System.Diagnostics.CodeAnalysis;

namespace Contoso.Requests.Clean;

/// <summary>Who manages each department. Ordinal, case-insensitive: the same in every culture.</summary>
public static class DepartmentManagers
{
    private static readonly FrozenDictionary<string, string> ManagerByDepartment =
        new Dictionary<string, string>
        {
            ["IT"] = "alex.demo",
            ["OPS"] = "jordan.demo",
            ["MKT"] = "riley.demo",
            ["HR"] = "riley.demo",
        }.ToFrozenDictionary(StringComparer.OrdinalIgnoreCase);

    public static bool TryFind(string department, [NotNullWhen(true)] out string? manager) =>
        ManagerByDepartment.TryGetValue(department, out manager);
}
