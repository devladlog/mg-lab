using System.Data.SqlClient;

namespace Contoso.Pricing
{
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
    }
}
