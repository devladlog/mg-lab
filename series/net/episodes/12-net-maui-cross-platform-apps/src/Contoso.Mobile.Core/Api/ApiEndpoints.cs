namespace Contoso.Mobile.Core.Api;

public static class ApiEndpoints
{
    public const int GatewayPort = 5311;   // the gateway of episode 11

    /// <summary>
    /// Where "localhost" is depends on where the app runs. Learn: the Android emulator sits behind a virtual router, and
    /// 10.0.2.2 is the alias of the development machine's loopback; Windows and the iOS simulator can use localhost.
    /// A physical device needs the machine's LAN address: pass it as <paramref name="overrideUrl"/> (the Settings page).
    /// </summary>
    public static Uri BaseAddress(string platform, string? overrideUrl = null)
    {
        if (!string.IsNullOrWhiteSpace(overrideUrl))
            return Uri.TryCreate(overrideUrl.Trim(), UriKind.Absolute, out var custom) && custom.Scheme is "http" or "https"
                ? custom
                : throw new ArgumentException($"'{overrideUrl}' is not an http(s) address.", nameof(overrideUrl));

        var host = platform.Equals("Android", StringComparison.OrdinalIgnoreCase) ? "10.0.2.2" : "localhost";
        return new Uri($"http://{host}:{GatewayPort}");
    }
}
