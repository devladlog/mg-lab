using Microsoft.PowerBI.Api;
using Microsoft.PowerBI.Api.Extensions;
using Microsoft.PowerBI.Api.Models;
using Microsoft.PowerBI.Api.Models.Credentials;
using Microsoft.Rest;
using Microsoft.Rest.Serialization;

namespace GatewayCredential;

/// <summary>
/// Builds the body of "Gateways - Create Datasource" with the credentials encrypted for the gateway,
/// using Microsoft's own AsymmetricKeyEncryptor (Learn: "Configure credentials programmatically").
/// The password is passed in, never read from a command line argument.
/// </summary>
public static class RequestBuilder
{
    public sealed record Options(
        string DataSourceType,
        string Server,
        string Database,
        string DataSourceName,
        string Username,
        string Password,
        string PrivacyLevel = "Organizational");

    public static PrivacyLevel ParsePrivacy(string name) => name.ToLowerInvariant() switch
    {
        "organizational" => PrivacyLevel.Organizational,
        "private" => PrivacyLevel.Private,
        "public" => PrivacyLevel.Public,
        "none" => PrivacyLevel.None,
        _ => throw new ArgumentException("privacy must be Organizational, Private, Public or None"),
    };

    public static string BuildJson(GatewayPublicKey publicKey, Options o)
    {
        // connectionDetails is a JSON *string* with exactly server and database (Learn's SQL example)
        var connection = System.Text.Json.JsonSerializer.Serialize(new Dictionary<string, string>
        {
            ["server"] = o.Server,
            ["database"] = o.Database,
        });

        var credentialDetails = new CredentialDetails(
            new BasicCredentials(o.Username, o.Password),
            ParsePrivacy(o.PrivacyLevel),
            EncryptedConnection.Encrypted,
            new AsymmetricKeyEncryptor(publicKey),
            null);

        var request = new PublishDatasourceToGatewayRequest(o.DataSourceType, connection, credentialDetails, o.DataSourceName);

        // The client is only used for its serializer settings: no call is made, no token is real.
        using var client = new PowerBIClient(new TokenCredentials("offline", "Bearer"));
        return SafeJsonConvert.SerializeObject(request, client.SerializationSettings);
    }
}
