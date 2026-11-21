using System.Security.Cryptography;
using System.Text.Json;
using Microsoft.PowerBI.Api.Models;

namespace GatewayCredential;

public static class Program
{
    public const string PasswordVariable = "GATEWAY_DS_PASSWORD";

    private const string Usage = @"gateway-credential: build the body for 'Gateways - Create Datasource' with encrypted credentials.

  gateway-credential --public-key-file <file> --server <s> --database <d> --name <display name> --username <u>
                     [--type Sql] [--privacy Organizational|Private|Public|None]
  gateway-credential --self-test

The gateway's public key is the 'publicKey' object ({ ""exponent"": ..., ""modulus"": ... }) from 'Gateways - Get Gateways'.
The password is read from the environment variable GATEWAY_DS_PASSWORD, never from the command line.
Output: the JSON request body on standard output.";

    public static int Main(string[] args)
    {
        try
        {
            if (args.Length == 0 || args.Contains("--help") || args.Contains("-h")) { Console.Error.WriteLine(Usage); return args.Length == 0 ? 2 : 0; }
            if (args.Contains("--self-test")) return SelfTest.Run(Console.Out);
            return Run(ParseArgs(args), Environment.GetEnvironmentVariable(PasswordVariable), Console.Out);
        }
        catch (ArgumentException e)
        {
            Console.Error.WriteLine($"error: {e.Message}");
            return 2;
        }
    }

    public static Dictionary<string, string> ParseArgs(string[] args)
    {
        var map = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        for (var i = 0; i < args.Length; i++)
        {
            var a = args[i];
            if (!a.StartsWith("--")) throw new ArgumentException($"unexpected argument '{a}'");
            if (a.Equals("--password", StringComparison.OrdinalIgnoreCase))
                throw new ArgumentException($"there is no --password: set {PasswordVariable} instead, so it never lands in a shell history");
            if (i + 1 >= args.Length) throw new ArgumentException($"{a} needs a value");
            map[a[2..]] = args[++i];
        }
        return map;
    }

    public static int Run(Dictionary<string, string> a, string? password, TextWriter output)
    {
        string Need(string k) => a.TryGetValue(k, out var v) && v.Length > 0 ? v : throw new ArgumentException($"--{k} is required");
        if (string.IsNullOrEmpty(password)) throw new ArgumentException($"{PasswordVariable} is not set");

        var keyJson = File.ReadAllText(Need("public-key-file"));
        var key = JsonSerializer.Deserialize<GatewayPublicKey>(keyJson, new JsonSerializerOptions { PropertyNameCaseInsensitive = true })
                  ?? throw new ArgumentException("the public key file is empty");
        if (string.IsNullOrEmpty(key.Exponent) || string.IsNullOrEmpty(key.Modulus))
            throw new ArgumentException("the public key needs 'exponent' and 'modulus'");

        var privacy = a.GetValueOrDefault("privacy", "Organizational");
        RequestBuilder.ParsePrivacy(privacy); // fail early with a clear message

        output.WriteLine(RequestBuilder.BuildJson(key, new RequestBuilder.Options(
            a.GetValueOrDefault("type", "Sql"), Need("server"), Need("database"), Need("name"), Need("username"), password, privacy)));
        return 0;
    }
}

/// <summary>Runs without a gateway: makes an RSA key, shapes it like Get Gateways' publicKey and checks the request body.</summary>
public static class SelfTest
{
    public static int Run(TextWriter output)
    {
        var failures = 0;
        void Check(bool ok, string what) { output.WriteLine($"{(ok ? "PASS" : "FAIL")}  {what}"); if (!ok) failures++; }

        foreach (var bits in new[] { 1024, 2048 })
        {
            // The SDK's encryptor for keys above 1024 bits uses Windows CNG (RSACng): it throws PlatformNotSupportedException elsewhere.
            if (bits > 1024 && !OperatingSystem.IsWindows())
            {
                output.WriteLine($"SKIP  {bits}-bit key: the SDK needs Windows CNG for keys above 1024 bits (run the self-test on the Windows laptop)");
                continue;
            }
            using var rsa = RSA.Create(bits);
            var rp = rsa.ExportParameters(false);
            var key = new GatewayPublicKey(Convert.ToBase64String(rp.Exponent!), Convert.ToBase64String(rp.Modulus!));
            var options = new RequestBuilder.Options("Sql", "10.50.0.30", "ContosoBikesDW", "Contoso Bikes DW", "pbi_gateway_reader", "Pa55-not-a-real-one!");

            var one = RequestBuilder.BuildJson(key, options);
            var two = RequestBuilder.BuildJson(key, options);
            using var doc = JsonDocument.Parse(one);
            var root = doc.RootElement;
            var cd = root.GetProperty("credentialDetails");

            Check(root.TryGetProperty("dataSourceName", out var dn) && dn.GetString() == "Contoso Bikes DW", $"{bits}-bit key: body has dataSourceName");
            Check(root.GetProperty("dataSourceType").GetString() == "Sql", $"{bits}-bit key: dataSourceType is Sql");
            Check(root.GetProperty("connectionDetails").GetString() == "{\"server\":\"10.50.0.30\",\"database\":\"ContosoBikesDW\"}", $"{bits}-bit key: connectionDetails is a JSON string with server and database");
            Check(cd.GetProperty("credentialType").GetString() == "Basic", $"{bits}-bit key: credentialType Basic");
            Check(cd.GetProperty("encryptedConnection").GetString() == "Encrypted", $"{bits}-bit key: encryptedConnection Encrypted");
            Check(cd.GetProperty("encryptionAlgorithm").GetString() == "RSA-OAEP", $"{bits}-bit key: encryptionAlgorithm RSA-OAEP");
            Check(cd.GetProperty("privacyLevel").GetString() == "Organizational", $"{bits}-bit key: privacyLevel Organizational");
            var creds = cd.GetProperty("credentials").GetString() ?? "";
            Check(creds.Length > 100 && IsBase64(creds), $"{bits}-bit key: credentials is base64 ({creds.Length} chars)");
            Check(!one.Contains("Pa55") && !one.Contains("pbi_gateway_reader"), $"{bits}-bit key: neither password nor user name appear in the clear");
            Check(one != two, $"{bits}-bit key: two runs give different ciphertext (randomized)");
        }
        output.WriteLine(failures == 0 ? "self-test: all passed" : $"self-test: {failures} failed");
        return failures == 0 ? 0 : 1;
    }

    private static bool IsBase64(string s)
    {
        try { _ = Convert.FromBase64String(s); return true; } catch (FormatException) { return false; }
    }
}
