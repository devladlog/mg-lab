using Contoso.Requests;

namespace Gotchas;

public static class NotExhaustive
{
    // Every state is handled, the base constructor is private... and the compiler still says CS8509,
    // because C# doesn't treat a class hierarchy as closed. Contrast with TypeScript unions (episode 1).
    public static string Badge(RequestState state) => state switch
    {
        RequestState.Draft => "grey",
        RequestState.Submitted => "blue",
        RequestState.Approved => "green",
        RequestState.Rejected => "red",
    };
}
