// Enterprise document intelligence: Document Intelligence (keyless) + a Flex Consumption Python function
// that the Power Automate flow calls. Based on the Learn quickstart "Create a function app on the Flex
// Consumption plan with Bicep" (managed identity to storage), plus the Document Intelligence account.

@description('Region for all resources. Document Intelligence and Flex Consumption must both be available there.')
param location string = resourceGroup().location

@description('Short token used in resource names.')
@minLength(3)
param resourceToken string = toLower(uniqueString(subscription().id, resourceGroup().id, location))

@description('S0 for real use. F0 (free) only analyzes the first two pages of a PDF and accepts files up to 4 MB.')
@allowed(['F0', 'S0'])
param docIntelSku string = 'S0'

@description('Routing policy, read by the function at run time (see src/docintel/rules.py).')
param minConfidence string = '0.80'
param approvalLimit string = '10000'
param allowedCurrencies string = 'EUR,GBP,USD'

var appName = 'func-inv-${resourceToken}'
var deploymentContainer = 'app-package-${take(appName, 32)}'

// Role definition IDs (Azure built-in roles)
var roles = {
  storageBlobDataOwner: 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b'
  storageQueueDataContributor: '974c5e8b-45b9-4653-ba55-5f855dd0fb88'
  storageTableDataContributor: '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3'
  monitoringMetricsPublisher: '3913510d-42f4-4e42-8a64-420c390055eb'
  cognitiveServicesUser: 'a97b65f3-24c7-4388-baec-2e87135dc908'
}

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${resourceToken}'
  location: location
  properties: {
    retentionInDays: 30
    sku: { name: 'PerGB2018' }
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${resourceToken}'
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
    DisableLocalAuth: true
  }
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: 'st${resourceToken}'
  location: location
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
  properties: {
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    minimumTlsVersion: 'TLS1_2'
    publicNetworkAccess: 'Enabled'
  }
  resource blob 'blobServices' = {
    name: 'default'
    resource container 'containers' = {
      name: deploymentContainer
      properties: { publicAccess: 'None' }
    }
  }
}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-inv-${resourceToken}'
  location: location
}

// Document Intelligence, keys disabled: callers need a Microsoft Entra token and the Cognitive Services User role.
// A custom subdomain is required for Microsoft Entra authentication.
resource docIntel 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: 'di-${resourceToken}'
  location: location
  kind: 'FormRecognizer'
  sku: { name: docIntelSku }
  properties: {
    customSubDomainName: 'di-${resourceToken}'
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
  }
}

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

resource docIntelRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(docIntel.id, identity.id, roles.cognitiveServicesUser)
  scope: docIntel
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.cognitiveServicesUser)
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

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
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identity.id}': {} }
  }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    siteConfig: { minTlsVersion: '1.2' }
    functionAppConfig: {
      deployment: {
        storage: {
          type: 'blobContainer'
          value: '${storage.properties.primaryEndpoints.blob}${deploymentContainer}'
          authentication: {
            type: 'UserAssignedIdentity'
            userAssignedIdentityResourceId: identity.id
          }
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
      DOCINTEL_ENDPOINT: docIntel.properties.endpoint
      AZURE_CLIENT_ID: identity.properties.clientId
      MIN_CONFIDENCE: minConfidence
      APPROVAL_LIMIT: approvalLimit
      ALLOWED_CURRENCIES: allowedCurrencies
    }
  }
  dependsOn: [storageRoles, docIntelRole, metricsRole]
}

output functionAppName string = functionApp.name
output extractUrl string = 'https://${functionApp.properties.defaultHostName}/api/invoices/extract'
output docIntelEndpoint string = docIntel.properties.endpoint
