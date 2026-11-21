using Kusto.Language;
using Kusto.Language.Symbols;

namespace Contoso.SecCopilotKit;

/// <summary>
/// The columns of the advanced hunting tables used in this episode, copied from the Microsoft Learn schema reference
/// (checked 2026-11-21). Only these tables are modelled: a query against another table is reported as "unchecked",
/// not as an error. Kusto.Language needs a schema to tell a typo from a column.
/// </summary>
public static class HuntingSchema
{
    public const string EmailEvents =
        "(Timestamp:datetime, NetworkMessageId:string, InternetMessageId:string, SenderMailFromAddress:string, SenderFromAddress:string, " +
        "SenderDisplayName:string, SenderObjectId:string, SenderMailFromDomain:string, SenderFromDomain:string, SenderIPv4:string, SenderIPv6:string, " +
        "RecipientEmailAddress:string, RecipientObjectId:string, Subject:string, EmailClusterId:long, EmailDirection:string, DeliveryAction:string, " +
        "DeliveryLocation:string, ThreatTypes:string, ThreatNames:string, DetectionMethods:string, ConfidenceLevel:string, BulkComplaintLevel:int, " +
        "EmailAction:string, EmailActionPolicy:string, EmailActionPolicyGuid:string, AuthenticationDetails:string, AttachmentCount:int, UrlCount:int, " +
        "EmailLanguage:string, Connectors:string, OrgLevelAction:string, OrgLevelPolicy:string, UserLevelAction:string, UserLevelPolicy:string, " +
        "ReportId:string, AdditionalFields:string, LatestDeliveryLocation:string, LatestDeliveryAction:string, OriginalThreatTypes:string, " +
        "OriginalDetectionMethods:string, OriginalConfidenceLevel:string, DistributionList:string, ExchangeTransportRule:string, " +
        "ForwardingInformation:string, Context:string, To:string, Cc:string, ThreatClassification:string, RecipientDomain:string, EmailSize:long, IsFirstContact:int)";

    public const string EntraIdSignInEvents =
        "(Timestamp:datetime, Application:string, ApplicationId:string, LogonType:string, EndpointCall:string, ErrorCode:int, CorrelationId:string, " +
        "SessionId:string, AccountDisplayName:string, AccountObjectId:string, AccountUpn:string, IsExternalUser:int, IsGuestUser:bool, " +
        "AlternateSignInName:string, LastPasswordChangeTimestamp:datetime, ResourceDisplayName:string, ResourceId:string, ResourceTenantId:string, " +
        "DeviceName:string, OSPlatform:string, DeviceTrustType:string, IsManaged:int, IsCompliant:int, AuthenticationProcessingDetails:string, " +
        "AuthenticationRequirement:string, TokenIssuerType:string, RiskLevelAggregated:int, RiskLevelDuringSignIn:int, RiskEventTypes:string, " +
        "RiskState:int, UserAgent:string, ClientAppUsed:string, Browser:string, ConditionalAccessPolicies:string, ConditionalAccessStatus:int, " +
        "IPAddress:string, Country:string, State:string, City:string, Latitude:string, Longitude:string, NetworkLocationDetails:string, " +
        "RequestId:string, ReportId:string, EntraIdDeviceId:string, GatewayJA4:string, TenantId:string, Type:string, SourceSystem:string, " +
        "TimeGenerated:datetime, UniqueTokenId:string, IsSignInThroughGlobalSecureAccess:bool)";

    public const string AlertInfo =
        "(Timestamp:datetime, AlertId:string, Title:string, Category:string, Severity:string, ServiceSource:string, DetectionSource:string, AttackTechniques:string)";

    /// <summary>Learn: on 19 October 2026 EntraIdSignInEvents replaced AADSignInEventsBeta; old queries are migrated automatically.</summary>
    public static readonly IReadOnlyDictionary<string, string> RenamedTables =
        new Dictionary<string, string>(StringComparer.Ordinal) { ["AADSignInEventsBeta"] = "EntraIdSignInEvents" };

    public static readonly IReadOnlyList<string> TableNames = new[] { "EmailEvents", "EntraIdSignInEvents", "AlertInfo" };

    public static GlobalState Globals { get; } = Build();

    private static GlobalState Build()
    {
        var db = new DatabaseSymbol("AdvancedHunting",
            new TableSymbol("EmailEvents", EmailEvents),
            new TableSymbol("EntraIdSignInEvents", EntraIdSignInEvents),
            new TableSymbol("AlertInfo", AlertInfo));
        return GlobalState.Default.WithCluster(new ClusterSymbol("hunting", db)).WithDatabase(db);
    }
}
