// C# 13 binds values.Average() to System.Linq.Enumerable.Average -> 2
System.Console.WriteLine($"C# 13: [1, 2, 3].Average() = {Gotchas.LinqClash.Which([1, 2, 3])}");
