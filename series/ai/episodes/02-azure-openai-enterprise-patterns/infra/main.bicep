// DEVLADLOG AI #2 — Azure OpenAI behind an AI gateway (API Management), keyless end to end.
//
//   app --(APIM subscription key)--> API Management (Basic v2) --(managed identity)--> Azure OpenAI primary
//                                       llm-token-limit per team                   \-> Azure OpenAI secondary
//                                       llm-emit-token-metric                         (priority pool + circuit breaker)
//
// Lab scope: public network access stays on, key auth is off. For network isolation use Standard v2 (outbound
// VNet integration) + private endpoints on the accounts + publicNetworkAccess 'Disabled'.
targetScope = 'resourceGroup'

@description('Short prefix for resource names (lowercase letters, digits, hyphens).')
@minLength(3)
@maxLength(16)
param prefix string = 'mglab-aoai'
param primaryLocation string = 'swedencentral'
param secondaryLocation string = 'germanywestcentral'
param modelName string = 'gpt-5-mini'
param modelVersion string = '2025-08-07'
@description('Deployment name; clients send it in the request "model" field. Same name in both regions.')
param deploymentName string = 'chat'
@allowed(['GlobalStandard', 'DataZoneStandard', 'Standard'])
@description('DataZoneStandard keeps processing inside the data zone of the resource (EU for EU regions).')
param deploymentSku string = 'DataZoneStandard'
@description('Capacity per region in units of 1,000 tokens per minute.')
param capacityPrimary int = 10
param capacitySecondary int = 10
param publisherEmail string
param publisherName string = 'Contoso AI Platform'
@description('Optional Entra object IDs of developers who may call Azure OpenAI directly (for troubleshooting).')
param developerObjectIds array = []
param teams array = ['hr-bot', 'sales-copilot']

var suffix = uniqueString(resourceGroup().id)
var tags = { workload: 'aoai-gateway', episode: 'devladlog-ai-02' }
var developers = [for id in developerObjectIds: { id: id, type: 'User' }]

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${prefix}-logs-${suffix}'
  location: primaryLocation
  tags: tags
  properties: { sku: { name: 'PerGB2018' }, retentionInDays: 30 }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: '${prefix}-ai-${suffix}'
  location: primaryLocation
  kind: 'web'
  tags: tags
  properties: { Application_Type: 'web', WorkspaceResourceId: logs.id }
}

resource apim 'Microsoft.ApiManagement/service@2024-05-01' = {
  name: '${prefix}-gw-${suffix}'
  location: primaryLocation
  tags: tags
  sku: { name: 'BasicV2', capacity: 1 }
  identity: { type: 'SystemAssigned' }
  properties: { publisherEmail: publisherEmail, publisherName: publisherName }
}

module primary 'modules/openai-account.bicep' = {
  name: 'aoai-primary'
  params: {
    name: '${prefix}-p-${suffix}'
    location: primaryLocation
    deploymentName: deploymentName
    modelName: modelName
    modelVersion: modelVersion
    deploymentSku: deploymentSku
    capacity: capacityPrimary
    inferencePrincipals: concat([{ id: apim.identity.principalId, type: 'ServicePrincipal' }], developers)
    tags: tags
  }
}

module secondary 'modules/openai-account.bicep' = {
  name: 'aoai-secondary'
  params: {
    name: '${prefix}-s-${suffix}'
    location: secondaryLocation
    deploymentName: deploymentName
    modelName: modelName
    modelVersion: modelVersion
    deploymentSku: deploymentSku
    capacity: capacitySecondary
    inferencePrincipals: concat([{ id: apim.identity.principalId, type: 'ServicePrincipal' }], developers)
    tags: tags
  }
}

// Application Insights logger + diagnostics with custom metrics enabled (needed by llm-emit-token-metric).
resource logger 'Microsoft.ApiManagement/service/loggers@2024-05-01' = {
  parent: apim
  name: 'appinsights'
  properties: {
    loggerType: 'applicationInsights'
    resourceId: appInsights.id
    credentials: { connectionString: appInsights.properties.ConnectionString }
  }
}

resource diagnostics 'Microsoft.ApiManagement/service/diagnostics@2024-05-01' = {
  parent: apim
  name: 'applicationinsights'
  properties: {
    loggerId: logger.id
    alwaysLog: 'allErrors'
    metrics: true
    sampling: { samplingType: 'fixed', percentage: 100 }
  }
}

// Azure OpenAI 429s can carry a long Retry-After; the breaker honours it (acceptRetryAfter) and APIM stops
// sending traffic to that backend for that time, so the pool moves to the next priority.
var breaker = {
  rules: [
    {
      name: 'throttled-or-failing'
      failureCondition: {
        count: 1
        interval: 'PT10S'
        statusCodeRanges: [ { min: 429, max: 429 }, { min: 500, max: 599 } ]
      }
      tripDuration: 'PT30S'
      acceptRetryAfter: true
    }
  ]
}

resource backendPrimary 'Microsoft.ApiManagement/service/backends@2024-05-01' = {
  parent: apim
  name: 'aoai-primary'
  properties: { url: primary.outputs.endpoint, protocol: 'http', circuitBreaker: breaker }
}

resource backendSecondary 'Microsoft.ApiManagement/service/backends@2024-05-01' = {
  parent: apim
  name: 'aoai-secondary'
  properties: { url: secondary.outputs.endpoint, protocol: 'http', circuitBreaker: breaker }
}

resource pool 'Microsoft.ApiManagement/service/backends@2024-05-01' = {
  parent: apim
  name: 'aoai-pool'
  properties: {
    description: 'Primary region first; secondary only when the primary breaker is open.'
    type: 'Pool'
    pool: {
      services: [
        { id: backendPrimary.id, priority: 1, weight: 1 }
        { id: backendSecondary.id, priority: 2, weight: 1 }
      ]
    }
  }
}

resource api 'Microsoft.ApiManagement/service/apis@2024-05-01' = {
  parent: apim
  name: 'aoai'
  properties: {
    displayName: 'Azure OpenAI (v1) via gateway'
    path: 'aoai'
    protocols: ['https']
    subscriptionRequired: true
    subscriptionKeyParameterNames: { header: 'api-key', query: 'api-key' }
  }
}

resource opChat 'Microsoft.ApiManagement/service/apis/operations@2024-05-01' = {
  parent: api
  name: 'chat-completions'
  properties: { displayName: 'Chat completions', method: 'POST', urlTemplate: '/openai/v1/chat/completions' }
}

resource opResponses 'Microsoft.ApiManagement/service/apis/operations@2024-05-01' = {
  parent: api
  name: 'responses'
  properties: { displayName: 'Responses', method: 'POST', urlTemplate: '/openai/v1/responses' }
}

resource apiPolicy 'Microsoft.ApiManagement/service/apis/policies@2024-05-01' = {
  parent: api
  name: 'policy'
  properties: { format: 'rawxml', value: loadTextContent('policies/aoai-api.xml') }
  dependsOn: [pool, diagnostics]
}

// One subscription (= one key and one token counter) per team.
resource subscriptions 'Microsoft.ApiManagement/service/subscriptions@2024-05-01' = [for team in teams: {
  parent: apim
  name: team
  properties: { displayName: team, scope: api.id, state: 'active' }
}]

output gatewayBaseUrl string = '${apim.properties.gatewayUrl}/aoai/openai/v1/'
output apimName string = apim.name
output primaryEndpoint string = primary.outputs.endpoint
output secondaryEndpoint string = secondary.outputs.endpoint
output appInsightsName string = appInsights.name
