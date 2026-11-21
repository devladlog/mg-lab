// DEVLADLOG AI #3: Azure AI Search (Basic) + Azure OpenAI (embeddings + chat), keyless end to end.
//  - Search: system-assigned identity (the vectorizer calls Azure OpenAI with it), API keys disabled, semantic
//    ranker on the free plan.
//  - Azure OpenAI: custom subdomain, key auth disabled, two pinned deployments.
//  - Roles: search identity -> Cognitive Services OpenAI User on the model account; the developer gets the three
//    search data/management roles plus OpenAI User.

@description('Short prefix for resource names (a unique suffix is appended).')
param prefix string = 'mglab-rag'
param location string = resourceGroup().location
@description('Object ID of the developer (or group) who runs ingest/evaluate/answer. Empty = no developer roles.')
param developerPrincipalId string = ''
@allowed(['User', 'Group', 'ServicePrincipal'])
param developerPrincipalType string = 'User'
@allowed(['basic', 'standard'])
param searchSku string = 'basic'

param embeddingDeployment string = 'embed-small'
param embeddingModel string = 'text-embedding-3-small'
param embeddingVersion string = '1'
@allowed(['GlobalStandard', 'DataZoneStandard', 'Standard'])
param embeddingSku string = 'Standard'
param embeddingCapacity int = 50

param chatDeployment string = 'chat'
param chatModel string = 'gpt-5-mini'
param chatVersion string = '2025-08-07'
@allowed(['GlobalStandard', 'DataZoneStandard', 'Standard'])
param chatSku string = 'DataZoneStandard'
param chatCapacity int = 10

var suffix = take(uniqueString(resourceGroup().id), 6)
var searchName = '${prefix}-srch-${suffix}'
var aoaiName = '${prefix}-aoai-${suffix}'
var roles = {
  openAiUser: '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
  searchServiceContributor: '7ca78c08-252a-4471-8644-bb5ff32d4ba0'
  searchIndexDataContributor: '8ebe5a00-799e-43f5-93ac-243d3dce84a7'
  searchIndexDataReader: '1407120a-92aa-4202-b7e9-c0e197c71c8f'
}
var developerSearchRoles = [roles.searchServiceContributor, roles.searchIndexDataContributor, roles.searchIndexDataReader]

resource search 'Microsoft.Search/searchServices@2025-05-01' = {
  name: searchName
  location: location
  sku: { name: searchSku }
  identity: { type: 'SystemAssigned' }
  properties: {
    replicaCount: 1
    partitionCount: 1
    hostingMode: 'Default'
    disableLocalAuth: true        // Entra ID + RBAC only; API keys stop working
    semanticSearch: 'free'        // monthly free allowance, then requests fail instead of billing
    publicNetworkAccess: 'enabled'
  }
}

resource aoai 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: aoaiName
  location: location
  kind: 'OpenAI'
  sku: { name: 'S0' }
  properties: {
    customSubDomainName: aoaiName // required for Entra ID auth
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
  }
}

resource embed 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: aoai
  name: embeddingDeployment
  sku: { name: embeddingSku, capacity: embeddingCapacity }
  properties: {
    model: { format: 'OpenAI', name: embeddingModel, version: embeddingVersion }
    versionUpgradeOption: 'NoAutoUpgrade'
  }
}

resource chat 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: aoai
  name: chatDeployment
  sku: { name: chatSku, capacity: chatCapacity }
  properties: {
    model: { format: 'OpenAI', name: chatModel, version: chatVersion }
    versionUpgradeOption: 'NoAutoUpgrade'
  }
  dependsOn: [embed] // one deployment operation at a time on the same account
}

// The vectorizer (no apiKey, no authIdentity) uses the search service's system-assigned identity.
resource searchToOpenAi 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(aoai.id, search.id, roles.openAiUser)
  scope: aoai
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.openAiUser)
    principalId: search.identity.principalId
    principalType: 'ServicePrincipal'
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

resource devToSearch 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for role in developerSearchRoles: if (!empty(developerPrincipalId)) {
  name: guid(search.id, developerPrincipalId, role)
  scope: search
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', role)
    principalId: developerPrincipalId
    principalType: developerPrincipalType
  }
}]

output searchEndpoint string = 'https://${search.name}.search.windows.net'
output aoaiEndpoint string = 'https://${aoai.name}.openai.azure.com'
output embeddingDeployment string = embed.name
output chatDeployment string = chat.name
