// NUnit runs tests one at a time unless you opt in. xUnit runs test classes in parallel by default.
// Fixtures (classes) in parallel; the tests inside one fixture still run one after another.
[assembly: Parallelizable(ParallelScope.Fixtures)]
