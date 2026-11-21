// DEVLADLOG Deep Dive #13: guest-join broker (Azure Functions, Flex Consumption, Node.js 24) + Azure Communication Services.
// No secrets anywhere: the app reaches storage (host + invite table) and ACS with one user-assigned managed identity,
// and the ACS resource has local (key) authentication switched off.

@description('Region of the function app and storage (Flex Consumption must be available there).')
param location string = resourceGroup().location

@description('Where ACS stores its data at rest. A geography name, not a region.')
@allowed(['Europe', 'United States', 'UK', 'Germany', 'France', 'Switzerland'])
param acsDataLocation string = 'Europe'

@minLength(3)
param resourceToken string = toLower(uniqueString(subscription().id, resourceGroup().id, location))

var appName = 'func-hyb-${resourceToken}'
var deploymentContainer = 'app-package-${take(appName, 32)}'
var inviteTable = 'invites'

var roles = {
  storageBlobDataOwner: 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b'
  storageTableDataContributor: '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3'
  communicationAndEmailServiceOwner: 'c2f4ef07-c644-48eb-af81-4b1b4947fb11'
  monitoringMetricsPublisher: '3913510d-42f4-4e42-8a64-420c390055eb'
}

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-hyb-${resourceToken}'
  location: location
  properties: {
    retentionInDays: 30
    sku: { name: 'PerGB2018' }
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-hyb-${resourceToken}'
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
    DisableLocalAuth: true
  }
}

// Code package, host state and the invite table. Shared keys off: only the identity below has data access.
resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: 'sthyb${resourceToken}'
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
  resource table 'tableServices' = {
    name: 'default'
    resource invites 'tables' = {
      name: inviteTable
    }
  }
}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-hyb-${resourceToken}'
  location: location
}

// The Communication Services resource. Location is always 'global'; dataLocation is where data at rest lives.
resource acs 'Microsoft.Communication/communicationServices@2025-09-01' = {
  name: 'acs-hyb-${resourceToken}'
  location: 'global'
  properties: {
    dataLocation: acsDataLocation
    disableLocalAuth: true
  }
}

resource blobOwner 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, identity.id, roles.storageBlobDataOwner)
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.storageBlobDataOwner)
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource tableContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, identity.id, roles.storageTableDataContributor)
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.storageTableDataContributor)
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// Scoped to the ACS resource only (not the resource group, not the subscription).
resource acsRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acs.id, identity.id, roles.communicationAndEmailServiceOwner)
  scope: acs
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.communicationAndEmailServiceOwner)
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource metricsRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(appInsights.id, identity.id, roles.monitoringMetricsPublisher)
  scope: appInsights
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.monitoringMetricsPublisher)
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource plan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: 'plan-hyb-${resourceToken}'
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
      scaleAndConcurrency: {
        maximumInstanceCount: 10 // also caps how fast a flood of guest requests can mint ACS identities
        instanceMemoryMB: 2048
      }
      runtime: { name: 'node', version: '24' }
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
      AZURE_CLIENT_ID: identity.properties.clientId // DefaultAzureCredential asks for this user-assigned identity
      Acs__Endpoint: 'https://${acs.properties.hostName}/'
      Invites__TableEndpoint: storage.properties.primaryEndpoints.table
      Invites__TableName: inviteTable
    }
  }
  dependsOn: [blobOwner, tableContributor, acsRole, metricsRole]
}

output functionAppName string = functionApp.name
output functionAppUrl string = 'https://${functionApp.properties.defaultHostName}'
output acsEndpoint string = 'https://${acs.properties.hostName}/'
output resourceGroupToDelete string = resourceGroup().name
