// DEVLADLOG Deep Dive #5: onboarding sync function (PowerShell 7.6 on Flex Consumption).
// No secrets anywhere: storage, Application Insights and Microsoft Graph are reached with one user-assigned identity.
// Graph app roles and the list grants are NOT Azure RBAC; provision/Grant-OnboardingAccess.ps1 assigns them.

@description('Region (Flex Consumption must be available there).')
param location string = resourceGroup().location

@minLength(3)
param resourceToken string = toLower(uniqueString(subscription().id, resourceGroup().id, location))

@description('Verified domain for new sign-in names, e.g. contoso.com.')
param upnDomain string

@description('NCRONTAB schedule of the sync pass. Every 5 minutes for the demo.')
param schedule string = '0 */5 * * * *'

@description('IDs printed by Grant-OnboardingAccess.ps1 and shown in the provisioning app (leave empty on the first deployment).')
param siteId string = ''
param requestsListId string = ''
param tasksListId string = ''
param provisioningServicePrincipalId string = ''
param provisioningJobId string = ''

var appName = 'func-onb-${resourceToken}'
var deploymentContainer = 'app-package-${take(appName, 32)}'

var roles = {
  storageBlobDataOwner: 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b'
  monitoringMetricsPublisher: '3913510d-42f4-4e42-8a64-420c390055eb'
}

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-onb-${resourceToken}'
  location: location
  properties: {
    retentionInDays: 30
    sku: { name: 'PerGB2018' }
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-onb-${resourceToken}'
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
    DisableLocalAuth: true
  }
}

// Code package + host storage (timer locks). Shared keys off: only the identity below has data access.
resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: 'stonb${resourceToken}'
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
  name: 'id-onb-${resourceToken}'
  location: location
}

// Timer triggers coordinate through blob storage; with an identity connection Learn asks for Blob Data Owner.
resource blobOwner 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, identity.id, roles.storageBlobDataOwner)
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.storageBlobDataOwner)
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
  name: 'plan-onb-${resourceToken}'
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
        maximumInstanceCount: 40
        instanceMemoryMB: 2048
      }
      runtime: { name: 'powershell', version: '7.6' } // 7.4 reached end of support in November 2026
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
      AZURE_CLIENT_ID: identity.properties.clientId // the token request asks for this user-assigned identity
      Onboarding__Schedule: schedule
      Onboarding__UpnDomain: upnDomain
      Onboarding__TimeZone: 'Europe/Lisbon'
      Onboarding__StartHour: '9'
      Onboarding__SentTimeoutMinutes: '60'
      Onboarding__SiteId: siteId
      Onboarding__RequestsListId: requestsListId
      Onboarding__TasksListId: tasksListId
      Onboarding__ProvisioningServicePrincipalId: provisioningServicePrincipalId
      Onboarding__ProvisioningJobId: provisioningJobId
    }
  }
  dependsOn: [blobOwner, metricsRole]
}

output functionAppName string = functionApp.name
output identityClientId string = identity.properties.clientId
output identityPrincipalId string = identity.properties.principalId
output identityName string = identity.name
