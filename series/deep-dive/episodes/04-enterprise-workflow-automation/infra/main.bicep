// DEVLADLOG Deep Dive #4: invoice approval orchestration (Durable Functions on Flex Consumption + Service Bus Basic).
// Everything the function app touches uses its user-assigned managed identity. The only shared-key credential is a
// Send-only SAS policy on ONE queue, for the Power Automate "Invoice ready" flow.

@description('Region for all resources (Flex Consumption must be available there).')
param location string = resourceGroup().location

@minLength(3)
param resourceToken string = toLower(uniqueString(subscription().id, resourceGroup().id, location))

@description('Approvers (lab users).')
param managerEmail string
param financeEmail string
param escalationEmail string

param financeThreshold int = 5000

@description('How long each approver has before the request escalates. Two days in production, a few minutes for the demo.')
@minValue(1)
param stageTimeoutMinutes int = 2880

@description('Empty: the flow trigger URL (with its SAS signature, stored in Key Vault) is the credential. Set to https://service.flow.microsoft.com/ to call the trigger with the managed identity instead.')
param flowAudience string = ''

@description('Always-ready instances for the "durable" group. Learn recommends 1 for Durable Functions on Flex Consumption; 0 keeps the lab free of baseline cost.')
@minValue(0)
param durableAlwaysReady int = 0

var appName = 'func-appr-${resourceToken}'
var deploymentContainer = 'app-package-${take(appName, 32)}'
var queueName = 'invoice-approvals'

var roles = {
  storageBlobDataOwner: 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b'
  storageQueueDataContributor: '974c5e8b-45b9-4653-ba55-5f855dd0fb88'
  storageTableDataContributor: '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3'
  monitoringMetricsPublisher: '3913510d-42f4-4e42-8a64-420c390055eb'
  serviceBusDataReceiver: '4f6d3b9b-027b-4f4c-9142-0e5a2a2247e0'
  keyVaultSecretsUser: '4633458b-17de-408a-b874-0445c86b69e6'
}

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-appr-${resourceToken}'
  location: location
  properties: {
    retentionInDays: 30
    sku: { name: 'PerGB2018' }
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-appr-${resourceToken}'
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
    DisableLocalAuth: true
  }
}

// Holds the code package AND the Durable task hub (queues, tables, blobs). Write access to the task hub can change
// what the app does, so no shared keys and only this identity has data roles.
resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: 'stappr${resourceToken}'
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
  name: 'id-appr-${resourceToken}'
  location: location
}

resource serviceBus 'Microsoft.ServiceBus/namespaces@2024-01-01' = {
  name: 'sb-appr-${resourceToken}'
  location: location
  sku: { name: 'Basic', tier: 'Basic' } // queues only; no topics, no duplicate detection
  properties: {
    minimumTlsVersion: '1.2'
    disableLocalAuth: false // the flow's Send-only SAS policy needs it
  }
  resource queue 'queues' = {
    name: queueName
    properties: {
      maxDeliveryCount: 5 // a message that keeps failing goes to the dead-letter queue
      lockDuration: 'PT1M'
      defaultMessageTimeToLive: 'P14D'
      deadLetteringOnMessageExpiration: true
    }
    resource flowSend 'authorizationRules' = {
      name: 'flow-send'
      properties: { rights: ['Send'] }
    }
  }
}

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: 'kv-appr-${resourceToken}'
  location: location
  properties: {
    tenantId: tenant().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
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

// Receiver on the one queue only. Learn: without Data Owner the scale controller falls back to peek-based
// message counts. At a few invoices an hour that is the right trade for least privilege.
resource queueReceiver 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(serviceBus::queue.id, identity.id, roles.serviceBusDataReceiver)
  scope: serviceBus::queue
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.serviceBusDataReceiver)
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource secretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, identity.id, roles.keyVaultSecretsUser)
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.keyVaultSecretsUser)
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
  name: 'plan-appr-${resourceToken}'
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
    keyVaultReferenceIdentity: identity.id // resolve @Microsoft.KeyVault(...) with the user-assigned identity
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
        maximumInstanceCount: 40
        instanceMemoryMB: 2048
        alwaysReady: durableAlwaysReady > 0 ? [{ name: 'durable', instanceCount: durableAlwaysReady }] : []
      }
      runtime: { name: 'dotnet-isolated', version: '10.0' }
    }
  }
  resource settings 'config' = {
    name: 'appsettings'
    properties: {
      AzureWebJobsStorage__accountName: storage.name
      AzureWebJobsStorage__credential: 'managedidentity'
      AzureWebJobsStorage__clientId: identity.properties.clientId
      ServiceBus__fullyQualifiedNamespace: '${serviceBus.name}.servicebus.windows.net'
      ServiceBus__credential: 'managedidentity'
      ServiceBus__clientId: identity.properties.clientId
      InvoiceQueueName: queueName
      APPLICATIONINSIGHTS_CONNECTION_STRING: appInsights.properties.ConnectionString
      APPLICATIONINSIGHTS_AUTHENTICATION_STRING: 'ClientId=${identity.properties.clientId};Authorization=AAD'
      AZURE_CLIENT_ID: identity.properties.clientId // DefaultAzureCredential in our code picks the same identity
      Approval__ManagerEmail: managerEmail
      Approval__FinanceEmail: financeEmail
      Approval__EscalationEmail: escalationEmail
      Approval__FinanceThreshold: string(financeThreshold)
      Approval__StageTimeoutMinutes: string(stageTimeoutMinutes)
      Callback__BaseUrl: 'https://${appName}.azurewebsites.net/'
      Callback__SigningKey: '@Microsoft.KeyVault(VaultName=${keyVault.name};SecretName=callback-signing-key)'
      Flow__Url: '@Microsoft.KeyVault(VaultName=${keyVault.name};SecretName=approval-flow-url)'
      Flow__Audience: flowAudience
    }
  }
  dependsOn: [storageRoles, queueReceiver, secretsUser, metricsRole]
}

output functionAppName string = functionApp.name
output identityPrincipalId string = identity.properties.principalId
output keyVaultName string = keyVault.name
output serviceBusNamespace string = serviceBus.name
output queueName string = queueName
output flowSendRuleName string = serviceBus::queue::flowSend.name
