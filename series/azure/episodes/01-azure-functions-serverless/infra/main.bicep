// Order intake on Azure Functions Flex Consumption (.NET 10 isolated worker).
// No storage keys anywhere: one user-assigned managed identity for host storage,
// the deployment container, the "OrdersStorage" binding connection and Application Insights.
// Based on the Flex Consumption Bicep quickstart on Microsoft Learn.

targetScope = 'resourceGroup'

@description('Region. Check: az functionapp list-flexconsumption-locations')
param location string = resourceGroup().location

@description('Short prefix for resource names (lowercase letters and digits).')
@minLength(3)
@maxLength(10)
param prefix string = 'orders'

@description('Upper limit for scale-out. Keep it low in a lab.')
@minValue(40)
@maxValue(1000)
param maximumInstanceCount int = 40

@allowed([512, 2048, 4096])
param instanceMemoryMB int = 2048

param tags object = {
  workload: 'order-intake'
  environment: 'lab'
}

var token = toLower(uniqueString(subscription().id, resourceGroup().id, prefix))
var appName = 'func-${prefix}-${token}'
var deploymentContainer = 'app-package-${take(token, 7)}'

// Built-in role definition IDs (same values in every tenant)
var roles = {
  blobDataOwner: 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b'
  queueDataContributor: '974c5e8b-45b9-4653-ba55-5f855dd0fb88'
  tableDataContributor: '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3'
  monitoringMetricsPublisher: '3913510d-42f4-4e42-8a64-420c390055eb'
}

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${prefix}-${token}'
  location: location
  tags: tags
  properties: {
    retentionInDays: 30
    sku: { name: 'PerGB2018' }
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${prefix}-${token}'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logs.id
    DisableLocalAuth: true // Entra ID only, no instrumentation-key ingestion
  }
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: take('st${prefix}${token}', 24)
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
  properties: {
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false // keys disabled: identity or nothing
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
  }

  resource blobs 'blobServices' = {
    name: 'default'
    resource packages 'containers' = { name: deploymentContainer }
    resource processed 'containers' = { name: 'orders-processed' }
  }

  resource queues 'queueServices' = {
    name: 'default'
    resource orders 'queues' = { name: 'orders' }
    resource poison 'queues' = { name: 'orders-poison' }
  }
}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${prefix}-${token}'
  location: location
  tags: tags
}

resource storageRoles 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for role in [roles.blobDataOwner, roles.queueDataContributor, roles.tableDataContributor]: {
    name: guid(storage.id, identity.id, role)
    scope: storage
    properties: {
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', role)
      principalId: identity.properties.principalId
      principalType: 'ServicePrincipal'
    }
  }
]

resource telemetryRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(appInsights.id, identity.id, roles.monitoringMetricsPublisher)
  scope: appInsights
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.monitoringMetricsPublisher)
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource plan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: 'plan-${prefix}-${token}'
  location: location
  tags: tags
  kind: 'functionapp'
  sku: {
    tier: 'FlexConsumption'
    name: 'FC1'
  }
  properties: {
    reserved: true // Linux
  }
}

resource app 'Microsoft.Web/sites@2024-04-01' = {
  name: appName
  location: location
  tags: tags
  kind: 'functionapp,linux'
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identity.id}': {} }
  }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    siteConfig: {
      minTlsVersion: '1.2'
    }
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
        maximumInstanceCount: maximumInstanceCount
        instanceMemoryMB: instanceMemoryMB
      }
      runtime: {
        name: 'dotnet-isolated'
        version: '10.0'
      }
    }
  }

  resource settings 'config' = {
    name: 'appsettings'
    properties: {
      // Host storage (identity-based)
      AzureWebJobsStorage__accountName: storage.name
      AzureWebJobsStorage__credential: 'managedidentity'
      AzureWebJobsStorage__clientId: identity.properties.clientId
      // Binding connection used by the three functions: separate name, same identity
      OrdersStorage__queueServiceUri: storage.properties.primaryEndpoints.queue
      OrdersStorage__blobServiceUri: storage.properties.primaryEndpoints.blob
      OrdersStorage__credential: 'managedidentity'
      OrdersStorage__clientId: identity.properties.clientId
      // Telemetry with Entra ID auth
      APPLICATIONINSIGHTS_CONNECTION_STRING: appInsights.properties.ConnectionString
      APPLICATIONINSIGHTS_AUTHENTICATION_STRING: 'ClientId=${identity.properties.clientId};Authorization=AAD'
    }
  }

  dependsOn: [storageRoles, telemetryRole]
}

output functionAppName string = app.name
output functionAppHost string = app.properties.defaultHostName
output storageAccountName string = storage.name
