using System.Security.Cryptography;
using System.Text;

namespace Contoso.InvoiceApproval;

/// <summary>
/// A callback URL that works for ONE pending approval request: HMAC-SHA256 over instance ID and request ID.
/// The flow stores no secret; a leaked URL can only answer a request that is still waiting for that approver.
/// </summary>
public sealed class CallbackSigner
{
    readonly byte[] _key;

    public CallbackSigner(byte[] key)
    {
        if (key.Length < 32) throw new ArgumentException("The signing key must be at least 32 bytes.", nameof(key));
        _key = key;
    }

    public static CallbackSigner FromBase64(string? base64)
    {
        if (string.IsNullOrWhiteSpace(base64))
            throw new InvalidOperationException("Callback:SigningKey is not set (Key Vault reference in Azure).");
        return new CallbackSigner(Convert.FromBase64String(base64));
    }

    public string Sign(string instanceId, string requestId) =>
        Base64Url(HMACSHA256.HashData(_key, Encoding.UTF8.GetBytes($"{instanceId}\n{requestId}")));

    public bool Verify(string instanceId, string requestId, string? signature)
    {
        if (string.IsNullOrEmpty(signature)) return false;
        var expected = Encoding.ASCII.GetBytes(Sign(instanceId, requestId));
        var actual = Encoding.ASCII.GetBytes(signature);
        return CryptographicOperations.FixedTimeEquals(expected, actual);   // no timing side channel
    }

    public Uri CallbackUrl(Uri baseUrl, string instanceId, string requestId) =>
        new(baseUrl, $"api/approvals/{Uri.EscapeDataString(instanceId)}/{requestId}/decision?sig={Sign(instanceId, requestId)}");

    static string Base64Url(byte[] bytes) => Convert.ToBase64String(bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_');
}
