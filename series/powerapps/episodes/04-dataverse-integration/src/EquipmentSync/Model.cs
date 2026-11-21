namespace EquipmentSync;

/// <summary>
/// The Equipment table from episode 1 (publisher prefix contoso, choice values = 41500 * 10000 + index).
/// Logical names are lower case; the schema names were contoso_Equipment, contoso_AssetTag, ...
/// </summary>
public static class Equipment
{
    public const string Table = "contoso_equipment";
    public const string Id = "contoso_equipmentid";
    public const string Name = "contoso_name";
    public const string AssetTag = "contoso_assettag";       // the alternate key column
    public const string Category = "contoso_category";
    public const string SerialNumber = "contoso_serialnumber";
    public const string PurchaseDate = "contoso_purchasedate";
    public const string Status = "contoso_status";
    public const string KeyName = "contoso_assettagkey";
    public const string KeySchemaName = "contoso_AssetTagKey";

    public static readonly IReadOnlyDictionary<string, int> Categories = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase)
    {
        ["Laptop"] = 415000000, ["Monitor"] = 415000001, ["Phone"] = 415000002, ["Accessory"] = 415000003,
    };

    public const int Available = 415000000, OnLoan = 415000001, InRepair = 415000002, Retired = 415000003;

    public static readonly IReadOnlyDictionary<int, string> StatusNames = new Dictionary<int, string>
    {
        [Available] = "Available", [OnLoan] = "On loan", [InRepair] = "In repair", [Retired] = "Retired",
    };
}

/// <summary>One valid row from the asset register export.</summary>
/// <param name="RegisterStatus">in_service, in_repair or retired, as the register calls them.</param>
public sealed record AssetRow(int Line, string AssetTag, string Name, string Category, string? SerialNumber, DateOnly? PurchaseDate, string RegisterStatus);

public enum RowOutcome { Created, Updated, Failed, Rejected }

public sealed record RowResult(int Line, string AssetTag, RowOutcome Outcome, string? Message = null);
