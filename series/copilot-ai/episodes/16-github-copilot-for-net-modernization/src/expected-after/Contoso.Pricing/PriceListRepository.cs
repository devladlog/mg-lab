using Microsoft.Data.SqlClient;

namespace Contoso.Pricing;

public class PriceListRepository
{
    private readonly string _connectionString;

    public PriceListRepository(string connectionString)
    {
        _connectionString = connectionString;
    }

    /// <summary>List price for a SKU, or null when the SKU is not in the price list.</summary>
    public decimal? GetListPrice(string sku)
    {
        using var connection = new SqlConnection(_connectionString);
        using var command = new SqlCommand("SELECT ListPrice FROM dbo.PriceList WHERE Sku = @sku", connection);
        command.Parameters.AddWithValue("@sku", sku);
        connection.Open();
        var value = command.ExecuteScalar();
        return value == null ? null : (decimal)value;
    }
}
