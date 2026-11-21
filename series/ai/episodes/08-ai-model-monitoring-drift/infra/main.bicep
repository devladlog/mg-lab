// DEVLADLOG AI #8: monitoring the HR bot in production, keyless end to end.
//  - Log Analytics + workspace-based Application Insights with local auth disabled (Entra-only ingestion)
//  - Azure OpenAI (keys off) with gpt-5-mini pinned on an EU data zone deployment; platform metrics and
//    request-usage logs to the same workspace
//  - A log search alert rule that fires when the drift monitor reports PSI >= 0.2
//  - Roles for the developer: call the model, send telemetry, query the workspace

@description('Short prefix for resource names (a unique suffix is appended).')
param prefix string = 'mglab-mon'
param location string = resourceGroup().location
@description('Object ID of the person (or group) who runs traffic and the monitor. Empty = no role assignments.')
param developerPrincipalId string = ''
@allowed(['User', 'Group', 'ServicePrincipal'])
param developerPrincipalType string = 'User'
param chatModel string = 'gpt-5-mini'
param chatVersion string = '2025-08-07'
@allowed(['DataZoneStandard', 'Standard', 'GlobalStandard'])
param chatSku string = 'DataZoneStandard'
param chatCapacity int = 20
@description('PSI at or above this value in a drift_report record fires the alert (Learn: >= 0.2 is significant).')
param psiAlertThreshold string = '0.2'

var suffix = take(uniqueString(resourceGroup().id), 6)
var roles = {
  openAiUser: '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd' // Cognitive Services OpenAI User
  metricsPublisher: '3913510d-42f4-4e42-8a64-420c390055eb' // Monitoring Metrics Publisher (Entra ingestion)
  logAnalyticsReader: '73c42c96-874c-492b-b04d-ab87d138a893' // Log Analytics Reader
}
var driftQuery = 'AppTraces | where Message == "drift_report" | extend max_psi = todouble(Properties["hr_max_psi"]) | where max_psi >= ${psiAlertThreshold}'

resource law 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${prefix}-law-${suffix}'
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource appi 'Microsoft.Insights/components@2020-02-02' = {
  name: '${prefix}-appi-${suffix}'
  location: location
  kind: 'other'
  properties: {
    Application_Type: 'other'
    WorkspaceResourceId: law.id
    DisableLocalAuth: true // ingestion only with an Entra token (Monitoring Metrics Publisher)
  }
}

resource aoai 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: '${prefix}-aoai-${suffix}'
  location: location
  kind: 'OpenAI'
  sku: { name: 'S0' }
  properties: {
    customSubDomainName: '${prefix}-aoai-${suffix}'
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
  }
}

resource chat 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: aoai
  name: 'chat'
  sku: { name: chatSku, capacity: chatCapacity }
  properties: {
    model: { format: 'OpenAI', name: chatModel, version: chatVersion }
    versionUpgradeOption: 'NoAutoUpgrade' // a silent model upgrade is drift you caused yourself
  }
}

resource aoaiDiag 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'to-log-analytics'
  scope: aoai
  properties: {
    workspaceId: law.id
    logs: [{ category: 'AzureOpenAIRequestUsage', enabled: true }]
    metrics: [{ category: 'AllMetrics', enabled: true }]
  }
}

resource driftAlert 'Microsoft.Insights/scheduledQueryRules@2023-12-01' = {
  name: '${prefix}-drift-alert'
  location: location
  properties: {
    displayName: 'HR bot: significant input or prediction drift'
    description: 'Fires when hrmon.monitor reports a feature with PSI >= ${psiAlertThreshold}.'
    severity: 2
    enabled: true
    scopes: [law.id]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT15M'
    autoMitigate: false
    criteria: {
      allOf: [
        {
          query: driftQuery
          timeAggregation: 'Count'
          operator: 'GreaterThan'
          threshold: 0
          failingPeriods: { numberOfEvaluationPeriods: 1, minFailingPeriodsToAlert: 1 }
        }
      ]
    }
  }
}

resource devToOpenAi 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(developerPrincipalId)) {
  name: guid(aoai.id, developerPrincipalId, roles.openAiUser)
  scope: aoai
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.openAiUser)
    principalId: developerPrincipalId
    principalType: developerPrincipalType
  }
}

resource devToAppInsights 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(developerPrincipalId)) {
  name: guid(appi.id, developerPrincipalId, roles.metricsPublisher)
  scope: appi
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.metricsPublisher)
    principalId: developerPrincipalId
    principalType: developerPrincipalType
  }
}

resource devToWorkspace 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(developerPrincipalId)) {
  name: guid(law.id, developerPrincipalId, roles.logAnalyticsReader)
  scope: law
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.logAnalyticsReader)
    principalId: developerPrincipalId
    principalType: developerPrincipalType
  }
}

output aoaiEndpoint string = 'https://${aoai.name}.openai.azure.com'
output aoaiName string = aoai.name
output appInsightsConnectionString string = appi.properties.ConnectionString // not a secret with local auth off
output workspaceId string = law.properties.customerId
output alertRuleName string = driftAlert.name
