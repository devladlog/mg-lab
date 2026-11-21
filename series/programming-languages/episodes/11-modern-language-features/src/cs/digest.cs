#:project Contoso.Digest/Contoso.Digest.csproj
#:property PublishAot=false

// A file-based app (.NET 10 SDK): no csproj for this file. File-based apps target native AOT by default,
// and System.Text.Json reflection is off under AOT, so this one opts out with PublishAot=false.
// Run it with
//   dotnet run src/cs/digest.cs -- samples/requests.json
using Contoso.Digest;

if (args is not [var path])
{
    Console.Error.WriteLine("usage: dotnet run digest.cs -- <requests.json>");
    return 2;
}

var digest = DigestBuilder.Build(DigestBuilder.Parse(File.ReadAllText(path)));
Console.Out.Write(DigestBuilder.Render(digest));
return 0;
