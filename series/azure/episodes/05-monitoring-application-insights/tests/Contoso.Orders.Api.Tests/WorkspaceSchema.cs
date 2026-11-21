using Kusto.Language;
using Kusto.Language.Symbols;

namespace Contoso.Orders.Api.Tests;

/// <summary>
/// Log Analytics workspace tables used by the queries, column for column as listed in the
/// Azure Monitor table reference on Microsoft Learn (learn.microsoft.com/azure/azure-monitor/reference/tables/...),
/// copied on 21 Nov 2026. Workspace-based Application Insights writes to these App* tables.
/// </summary>
public static class WorkspaceSchema
{
    public static readonly GlobalState Globals = GlobalState.Default.WithDatabase(new DatabaseSymbol("workspace",
        new TableSymbol("AppRequests",
            "(" + "AppRoleInstance:string, AppRoleName:string, AppVersion:string, _BilledSize:real," +
            "ClientBrowser:string, ClientCity:string, ClientCountryOrRegion:string, ClientIP:string," +
            "ClientModel:string, ClientOS:string, ClientStateOrProvince:string, ClientType:string," +
            "DurationMs:real, Id:string, IKey:string, _IsBillable:string, ItemCount:int, Measurements:dynamic," +
            "Name:string, OperationId:string, OperationName:string, ParentId:string, Properties:dynamic," +
            "ReferencedItemId:string, ReferencedType:string, ResourceGUID:string, _ResourceId:string," +
            "ResultCode:string, SDKVersion:string, SessionId:string, Source:string, SourceSystem:string," +
            "_SubscriptionId:string, Success:bool, SyntheticSource:string, TenantId:string," +
            "TimeGenerated:datetime, Type:string, Url:string, UserAccountId:string, UserAuthenticatedId:string," +
            "UserId:string" + ")"),
        new TableSymbol("AppDependencies",
            "(" + "AppRoleInstance:string, AppRoleName:string, AppVersion:string, _BilledSize:real," +
            "ClientBrowser:string, ClientCity:string, ClientCountryOrRegion:string, ClientIP:string," +
            "ClientModel:string, ClientOS:string, ClientStateOrProvince:string, ClientType:string, Data:string," +
            "DependencyType:string, DurationMs:real, Id:string, IKey:string, _IsBillable:string, ItemCount:int," +
            "Measurements:dynamic, Name:string, OperationId:string, OperationName:string, ParentId:string," +
            "Properties:dynamic, ReferencedItemId:string, ReferencedType:string, ResourceGUID:string," +
            "_ResourceId:string, ResultCode:string, SDKVersion:string, SessionId:string, SourceSystem:string," +
            "_SubscriptionId:string, Success:bool, SyntheticSource:string, Target:string, TenantId:string," +
            "TimeGenerated:datetime, Type:string, UserAccountId:string, UserAuthenticatedId:string," +
            "UserId:string" + ")"),
        new TableSymbol("AppExceptions",
            "(" + "AppRoleInstance:string, AppRoleName:string, AppVersion:string, Assembly:string, _BilledSize:real," +
            "ClientBrowser:string, ClientCity:string, ClientCountryOrRegion:string, ClientIP:string," +
            "ClientModel:string, ClientOS:string, ClientStateOrProvince:string, ClientType:string," +
            "Details:dynamic, ExceptionType:string, HandledAt:string, IKey:string, InnermostAssembly:string," +
            "InnermostMessage:string, InnermostMethod:string, InnermostType:string, _IsBillable:string," +
            "ItemCount:int, Measurements:dynamic, Message:string, Method:string, OperationId:string," +
            "OperationName:string, OuterAssembly:string, OuterMessage:string, OuterMethod:string," +
            "OuterType:string, ParentId:string, ProblemId:string, Properties:dynamic, ResourceGUID:string," +
            "_ResourceId:string, SDKVersion:string, SessionId:string, SeverityLevel:int, SourceSystem:string," +
            "_SubscriptionId:string, SyntheticSource:string, TenantId:string, TimeGenerated:datetime," +
            "Type:string, UserAccountId:string, UserAuthenticatedId:string, UserId:string" + ")"),
        new TableSymbol("AppTraces",
            "(" + "AppRoleInstance:string, AppRoleName:string, AppVersion:string, _BilledSize:real," +
            "ClientBrowser:string, ClientCity:string, ClientCountryOrRegion:string, ClientIP:string," +
            "ClientModel:string, ClientOS:string, ClientStateOrProvince:string, ClientType:string, IKey:string," +
            "_IsBillable:string, ItemCount:int, Measurements:dynamic, Message:string, OperationId:string," +
            "OperationName:string, ParentId:string, Properties:dynamic, ReferencedItemId:string," +
            "ReferencedType:string, ResourceGUID:string, _ResourceId:string, SDKVersion:string," +
            "SessionId:string, SeverityLevel:int, SourceSystem:string, _SubscriptionId:string," +
            "SyntheticSource:string, TenantId:string, TimeGenerated:datetime, Type:string, UserAccountId:string," +
            "UserAuthenticatedId:string, UserId:string" + ")"),
        new TableSymbol("AppMetrics",
            "(" + "AppRoleInstance:string, AppRoleName:string, AppVersion:string, _BilledSize:real," +
            "ClientBrowser:string, ClientCity:string, ClientCountryOrRegion:string, ClientIP:string," +
            "ClientModel:string, ClientOS:string, ClientStateOrProvince:string, ClientType:string, IKey:string," +
            "_IsBillable:string, ItemCount:int, Max:real, Min:real, Name:string, OperationId:string," +
            "OperationName:string, ParentId:string, Properties:dynamic, ResourceGUID:string, _ResourceId:string," +
            "SDKVersion:string, SessionId:string, SourceSystem:string, _SubscriptionId:string, Sum:real," +
            "SyntheticSource:string, TenantId:string, TimeGenerated:datetime, Type:string, UserAccountId:string," +
            "UserAuthenticatedId:string, UserId:string" + ")"),
        new TableSymbol("AppAvailabilityResults",
            "(" + "AppRoleInstance:string, AppRoleName:string, AppVersion:string, _BilledSize:real," +
            "ClientBrowser:string, ClientCity:string, ClientCountryOrRegion:string, ClientIP:string," +
            "ClientModel:string, ClientOS:string, ClientStateOrProvince:string, ClientType:string," +
            "DurationMs:real, Id:string, IKey:string, _IsBillable:string, ItemCount:int, Location:string," +
            "Measurements:dynamic, Message:string, Name:string, OperationId:string, OperationName:string," +
            "ParentId:string, Properties:dynamic, ResourceGUID:string, _ResourceId:string, SDKVersion:string," +
            "SessionId:string, SourceSystem:string, _SubscriptionId:string, Success:bool," +
            "SyntheticSource:string, TenantId:string, TimeGenerated:datetime, Type:string, UserAccountId:string," +
            "UserAuthenticatedId:string, UserId:string" + ")"),
        new TableSymbol("Usage",
            "(" + "AvgLatencyInSeconds:real, BatchesCapped:long, BatchesOutsideSla:long, BatchesWithinSla:long," +
            "_BilledSize:real, Computer:string, DataType:string, EndTime:datetime, IsBillable:bool," +
            "_IsBillable:string, LinkedMeterId:string, LinkedResourceUri:string, MeterId:string, Plan:string," +
            "Quantity:real, QuantityUnit:string, ResourceUri:string, Solution:string, SourceSystem:string," +
            "StartTime:datetime, TimeGenerated:datetime, TotalBatches:long, Type:string" + ")")));
}
