#:project ../../src/cs/Contoso.Digest/Contoso.Digest.csproj

// Wrong on purpose: the same app without `#:property PublishAot=false`.
// Run: dotnet run demo/cs/no-aot-flag.cs -- samples/requests.json
using Contoso.Digest;

var digest = DigestBuilder.Build(DigestBuilder.Parse(File.ReadAllText(args[0])));
Console.Out.Write(DigestBuilder.Render(digest));
