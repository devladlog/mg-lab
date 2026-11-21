namespace Contoso.Portfolio;

/// <summary>
/// A value or an error, never both. Select and SelectMany make it work with C# query syntax:
/// <c>from a in ParseA() from b in ParseB(a) select ...</c> stops at the first error.
/// </summary>
public readonly record struct Result<T>
{
    private readonly T? _value;
    public string? Error { get; }
    public bool IsOk => Error is null;
    public T Value => IsOk ? _value! : throw new InvalidOperationException($"No value: {Error}");

    // Create through Result.Ok / Result.Fail (CA1000: no static members on generic types).
    internal Result(T? value, string? error) => (_value, Error) = (value, error);

    public override string ToString() => IsOk ? $"Ok({_value})" : $"Fail({Error})";
}

public static class Result
{
    public static Result<T> Ok<T>(T value) => new(value, null);
    public static Result<T> Fail<T>(string error) => new(default, error);

    /// <summary>map: transform the value, pass an error through untouched.</summary>
    public static Result<TOut> Select<T, TOut>(this Result<T> result, Func<T, TOut> map) =>
        result.IsOk ? Ok(map(result.Value)) : Fail<TOut>(result.Error!);

    /// <summary>bind: the next step runs only if this one succeeded. This is what "from ... from ..." calls.</summary>
    public static Result<TOut> SelectMany<T, TMid, TOut>(
        this Result<T> result, Func<T, Result<TMid>> bind, Func<T, TMid, TOut> project)
    {
        if (!result.IsOk) return Fail<TOut>(result.Error!);
        var mid = bind(result.Value);
        return mid.IsOk ? Ok(project(result.Value, mid.Value)) : Fail<TOut>(mid.Error!);
    }
}
