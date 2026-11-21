namespace ProjectRequests.Grpc;

/// <summary>
/// Protobuf has no decimal type, and double would round money. This is the units + nanos format from Learn's
/// "Create Protobuf messages for .NET apps": 12345.6789 -> { Units = 12345, Nanos = 678900000 }.
/// Nine decimal places at most, which is plenty for a budget. Partial: the generated half has Units and Nanos.
/// </summary>
public partial class DecimalValue
{
    private const decimal NanoFactor = 1_000_000_000;

    public DecimalValue(long units, int nanos)
    {
        Units = units;
        Nanos = nanos;
    }

    public static implicit operator decimal(DecimalValue grpcDecimal) =>
        grpcDecimal.Units + grpcDecimal.Nanos / NanoFactor;

    public static implicit operator DecimalValue(decimal value)
    {
        var units = decimal.ToInt64(value);                      // truncates toward zero: -1.5 -> -1
        var nanos = decimal.ToInt32((value - units) * NanoFactor); // -0.5 -> -500000000, same sign as units
        return new DecimalValue(units, nanos);
    }
}
