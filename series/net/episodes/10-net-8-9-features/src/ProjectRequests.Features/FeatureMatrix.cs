namespace ProjectRequests.Features;

/// <summary>Which target this assembly was compiled for, and whether the .NET 9 / C# 13 code is in it.</summary>
public static class FeatureMatrix
{
#if NET10_0_OR_GREATER
    public const string CompiledFor = "net10.0";
#elif NET9_0_OR_GREATER
    public const string CompiledFor = "net9.0";
#else
    public const string CompiledFor = "net8.0";
#endif

#if NET9_0_OR_GREATER
    public const bool Net9FeaturesCompiledIn = true;
#else
    public const bool Net9FeaturesCompiledIn = false;
#endif
}
