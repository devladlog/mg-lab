using Microsoft.PowerFx;
using Microsoft.PowerFx.Types;

namespace ContosoInspections.PowerFx.Tests;

/// <summary>A table whose updates fail, like a Dataverse table the user can read but not write (no Write privilege).</summary>
public sealed class ReadOnlyTable(TableValue inner, string message) : TableValue(inner.Type)
{
    public override IEnumerable<DValue<RecordValue>> Rows => inner.Rows;

    // Engine variables must be copyable (RecalcEngine.UpdateVariable); this wrapper is immutable, so a "copy" is itself.
    public override bool CanShallowCopy => true;

    public override Task<DValue<RecordValue>> AppendAsync(RecordValue record, CancellationToken cancellationToken) =>
        Task.FromResult(DValue<RecordValue>.Of(FormulaValue.NewError(new ExpressionError { Message = message, Kind = ErrorKind.CreatePermission })));

    protected override Task<DValue<RecordValue>> PatchCoreAsync(RecordValue baseRecord, RecordValue changeRecord, CancellationToken cancellationToken) =>
        Task.FromResult(DValue<RecordValue>.Of(FormulaValue.NewError(new ExpressionError { Message = message, Kind = ErrorKind.EditPermissions })));
}
