using Microsoft.Data.SqlClient;

namespace Contoso.Pricing;

public static class ConnectionStrings
{
    /// <summary>SQL authentication string for the price list database. The password comes from the caller.</summary>
    public static string Build(string server, string database, string user, string password)
    {
        var builder = new SqlConnectionStringBuilder
        {
            DataSource = server,
            InitialCatalog = database,
            UserID = user,
            Password = password,
            ConnectTimeout = 15
        };
        return builder.ConnectionString;
    }

    /// <summary>
    /// LAB ONLY. Microsoft.Data.SqlClient encrypts by default, so a server that only has the self-signed certificate
    /// SQL Server generates fails the certificate check. Trusting the certificate removes that protection:
    /// install a real certificate on the server instead.
    /// </summary>
    public static string BuildTrustingServerCertificate(string server, string database, string user, string password)
    {
        var builder = new SqlConnectionStringBuilder(Build(server, database, user, password)) { TrustServerCertificate = true };
        return builder.ConnectionString;
    }
}
