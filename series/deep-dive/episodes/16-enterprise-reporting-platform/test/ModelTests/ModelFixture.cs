using Microsoft.AnalysisServices.Tabular;
using Xunit;

namespace ModelTests;

/// <summary>Loads the committed TMDL folder once with the same serializer Power BI Desktop and Fabric use.</summary>
public sealed class ModelFixture
{
    public string Folder { get; }
    public Database Database { get; }
    public Model Model => Database.Model;

    public ModelFixture()
    {
        Folder = Path.Combine(AppContext.BaseDirectory, "model", "definition");
        Database = TmdlSerializer.DeserializeDatabaseFromFolder(Folder);
    }

    public IEnumerable<Measure> AllMeasures => Model.Tables.SelectMany(t => t.Measures);
}

[CollectionDefinition("model")]
public sealed class ModelCollection : ICollectionFixture<ModelFixture> { }
