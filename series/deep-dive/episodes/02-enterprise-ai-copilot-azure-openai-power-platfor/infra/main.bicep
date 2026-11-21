// Enterprise AI copilot: Azure OpenAI (keyless) + Azure AI Search (keyless, integrated vectorizer)
// + a Flex Consumption Python function behind App Service authentication (Microsoft Entra ID).
// Every service-to-service call uses a managed identity; no keys are created or stored.

@description('Region for all resources. Check model availability for the chat deployment SKU there.')
param location string = resourceGroup().location

@minLength(3)
param resourceToken string = toLower(uniqueString(subscription().id, resourceGroup().id, location))

@description('Application (client) ID of the "HR Copilot API" app registration. Tokens must be issued for api://<this id>.')
param apiClientId string

@description('Object ID of whoever runs the ingestion job (you, or a pipeline identity).')
param ingestPrincipalId string

@allowed(['User', 'ServicePrincipal'])
param ingestPrincipalType string = 'User'

param chatModel string = 'gpt-5.4-mini'
param chatModelVersion string = '2026-03-17'
@description('DataZoneStandard keeps processing in the data zone (EU for EU regions). Verify availability for the model.')
param chatSku string = 'DataZoneStandard'
param chatCapacity int = 20
param embedSku string = 'Standard'
param embedCapacity int = 20

var roles = {
  storageBlobDataOwner: 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b'
  storageQueueDataContributor: '974c5e8b-45b9-4653-ba55-5f855dd0fb88'
  storageTableDataContributor: '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3'
  monitoringMetricsPublisher: '3913510d-42f4-4e42-8a64-420c390055eb'
  openAiUser: '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
  searchIndexDataReader: '1407120a-92aa-4202-b7e9-c0e197c71c8f'
  searchIndexDataContributor: '8ebe5a00-799e-43f5-93ac-243d3dce84a7'
  searchServiceContributor: '7ca78c08-252a-4471-8644-bb5ff32d4ba0'
}
var appName = 'func-copilot-${resourceToken}'
var deploymentContainer = 'app-package-${take(appName, 32)}'

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${resourceToken}'
  location: location
  properties: { retentionInDays: 30, sku: { name: 'PerGB2018' } }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${resourceToken}'
  location: location
  kind: 'web'
  properties: { Application_Type: 'web', WorkspaceResourceId: logAnalytics.id, DisableLocalAuth: true }
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: 'st${resourceToken}'
  location: location
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
  properties: { allowBlobPublicAccess: false, allowSharedKeyAccess: false, minimumTlsVersion: 'TLS1_2' }
  resource blob 'blobServices' = {
    name: 'default'
    resource container 'containers' = { name: deploymentContainer, properties: { publicAccess: 'None' } }
  }
}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-copilot-${resourceToken}'
  location: location
}

// ---- Azure OpenAI ------------------------------------------------------------------------------------
resource openai 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: 'aoai-${resourceToken}'
  location: location
  kind: 'OpenAI'
  sku: { name: 'S0' }
  properties: {
    customSubDomainName: 'aoai-${resourceToken}'
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
  }
}

resource embed 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: openai
  name: 'embed'
  sku: { name: embedSku, capacity: embedCapacity }
  properties: {
    model: { format: 'OpenAI', name: 'text-embedding-3-small', version: '1' }
    versionUpgradeOption: 'NoAutoUpgrade'
  }
}

resource chat 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: openai
  name: 'chat'
  sku: { name: chatSku, capacity: chatCapacity }
  properties: {
    model: { format: 'OpenAI', name: chatModel, version: chatModelVersion }
    versionUpgradeOption: 'NoAutoUpgrade'
  }
  dependsOn: [embed] // deployments on one account one at a time
}

// ---- Azure AI Search -----------------------------------------------------------------------------------
resource search 'Microsoft.Search/searchServices@2025-05-01' = {
  name: 'srch-${resourceToken}'
  location: location
  sku: { name: 'basic' }
  identity: { type: 'SystemAssigned' } // used by the vectorizer to call Azure OpenAI
  properties: {
    replicaCount: 1
    partitionCount: 1
    disableLocalAuth: true // RBAC only, no admin or query keys
    publicNetworkAccess: 'Enabled'
  }
}

// ---- Role assignments ------------------------------------------------------------------------------
resource storageRoles 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for r in ['storageBlobDataOwner', 'storageQueueDataContributor', 'storageTableDataContributor']: {
    name: guid(storage.id, identity.id, roles[r])
    scope: storage
    properties: {
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles[r])
      principalId: identity.properties.principalId
      principalType: 'ServicePrincipal'
    }
  }
]

resource metricsRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(appInsights.id, identity.id, roles.monitoringMetricsPublisher)
  scope: appInsights
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.monitoringMetricsPublisher)
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// function -> Azure OpenAI (chat) and Search (query only)
resource fnOpenAi 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(openai.id, identity.id, roles.openAiUser)
  scope: openai
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.openAiUser)
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource fnSearch 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(search.id, identity.id, roles.searchIndexDataReader)
  scope: search
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.searchIndexDataReader)
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// Search service identity -> Azure OpenAI (query-time vectorizer)
resource searchOpenAi 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(openai.id, search.id, roles.openAiUser)
  scope: openai
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.openAiUser)
    principalId: search.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// ingestion principal -> create the index, push documents, call the embedding model
resource ingestSearch 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for r in ['searchServiceContributor', 'searchIndexDataContributor']: {
    name: guid(search.id, ingestPrincipalId, roles[r])
    scope: search
    properties: {
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles[r])
      principalId: ingestPrincipalId
      principalType: ingestPrincipalType
    }
  }
]

resource ingestOpenAi 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(openai.id, ingestPrincipalId, roles.openAiUser)
  scope: openai
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.openAiUser)
    principalId: ingestPrincipalId
    principalType: ingestPrincipalType
  }
}

// ---- Function app ------------------------------------------------------------------------------------
resource plan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: 'plan-${resourceToken}'
  location: location
  kind: 'functionapp'
  sku: { tier: 'FlexConsumption', name: 'FC1' }
  properties: { reserved: true }
}

resource functionApp 'Microsoft.Web/sites@2024-04-01' = {
  name: appName
  location: location
  kind: 'functionapp,linux'
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${identity.id}': {} } }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    siteConfig: { minTlsVersion: '1.2' }
    functionAppConfig: {
      deployment: {
        storage: {
          type: 'blobContainer'
          value: '${storage.properties.primaryEndpoints.blob}${deploymentContainer}'
          authentication: { type: 'UserAssignedIdentity', userAssignedIdentityResourceId: identity.id }
        }
      }
      scaleAndConcurrency: { maximumInstanceCount: 40, instanceMemoryMB: 2048 }
      runtime: { name: 'python', version: '3.11' }
    }
  }

  resource settings 'config' = {
    name: 'appsettings'
    properties: {
      AzureWebJobsStorage__accountName: storage.name
      AzureWebJobsStorage__credential: 'managedidentity'
      AzureWebJobsStorage__clientId: identity.properties.clientId
      APPLICATIONINSIGHTS_CONNECTION_STRING: appInsights.properties.ConnectionString
      APPLICATIONINSIGHTS_AUTHENTICATION_STRING: 'ClientId=${identity.properties.clientId};Authorization=AAD'
      AZURE_CLIENT_ID: identity.properties.clientId
      OPENAI_ENDPOINT: 'https://${openai.properties.customSubDomainName}.openai.azure.com'
      CHAT_DEPLOYMENT: chat.name
      SEARCH_ENDPOINT: 'https://${search.name}.search.windows.net'
      SEARCH_INDEX: 'hr-policies'
    }
  }

  // App Service authentication: only tokens issued for the API app registration get through.
  // This is what makes X-MS-CLIENT-PRINCIPAL trustworthy in the function.
  resource auth 'config' = {
    name: 'authsettingsV2'
    properties: {
      platform: { enabled: true }
      globalValidation: {
        requireAuthentication: true
        unauthenticatedClientAction: 'Return401'
      }
      identityProviders: {
        azureActiveDirectory: {
          enabled: true
          registration: {
            clientId: apiClientId
            openIdIssuer: '${environment().authentication.loginEndpoint}${tenant().tenantId}/v2.0'
          }
          validation: { allowedAudiences: ['api://${apiClientId}'] }
        }
      }
      login: { tokenStore: { enabled: false } }
    }
  }
  dependsOn: [storageRoles, metricsRole, fnOpenAi, fnSearch]
}

output functionAppName string = functionApp.name
output askUrl string = 'https://${functionApp.properties.defaultHostName}/api/ask'
output openAiEndpoint string = 'https://${openai.properties.customSubDomainName}.openai.azure.com'
output searchEndpoint string = 'https://${search.name}.search.windows.net'
