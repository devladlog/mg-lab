// DEVLADLOG Deep Dive #3: Contoso purchase requests API.
// Lowest-cost lab footprint: App Service F1 (free, Linux), Azure SQL Database free offer (serverless GP, auto-pause at
// the monthly free limit), Log Analytics + Application Insights (pay per GB ingested).
// No passwords anywhere: SQL is Microsoft Entra-only, the web app reaches it with its system-assigned identity.

targetScope = 'resourceGroup'

@description('Region for all resources.')
param location string = resourceGroup().location

@description('Short prefix for resource names.')
@maxLength(12)
param namePrefix string = 'purchreq'

@description('Tenant ID of the Microsoft Entra tenant (GUID).')
param tenantId string = tenant().tenantId

@description('Client ID of the "Contoso Purchase Requests API" app registration.')
param apiClientId string

@description('Display name of the Entra group (or user) that administers the SQL server.')
param sqlAdminLogin string

@description('Object ID of that group or user.')
param sqlAdminObjectId string

@allowed(['Group', 'User'])
param sqlAdminPrincipalType string = 'Group'

@description('Finance threshold for approvals, in EUR.')
param financeThreshold int = 5000

var suffix = uniqueString(resourceGroup().id)
var webAppName = 'app-${namePrefix}-${suffix}'
var sqlServerName = 'sql-${namePrefix}-${suffix}'
var databaseName = 'purchase-requests'

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${namePrefix}-${suffix}'
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${namePrefix}-${suffix}'
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logs.id
  }
}

resource sqlServer 'Microsoft.Sql/servers@2023-08-01' = {
  name: sqlServerName
  location: location
  properties: {
    minimalTlsVersion: '1.2'
    publicNetworkAccess: 'Enabled'
    administrators: {
      administratorType: 'ActiveDirectory'
      azureADOnlyAuthentication: true // no SQL logins, no passwords
      login: sqlAdminLogin
      sid: sqlAdminObjectId
      tenantId: tenantId
      principalType: sqlAdminPrincipalType
    }
  }
}

// F1 has no virtual network integration, so the app reaches SQL over the public endpoint.
// This rule admits ANY Azure-hosted client (other customers too); only Entra identities with a database user get in.
// Production: Basic or higher + VNet integration + private endpoint, and remove this rule.
resource allowAzure 'Microsoft.Sql/servers/firewallRules@2023-08-01' = {
  parent: sqlServer
  name: 'AllowAllWindowsAzureIps'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

resource database 'Microsoft.Sql/servers/databases@2023-08-01' = {
  parent: sqlServer
  name: databaseName
  location: location
  sku: {
    name: 'GP_S_Gen5_2'
    tier: 'GeneralPurpose'
    family: 'Gen5'
    capacity: 2
  }
  properties: {
    useFreeLimit: true
    freeLimitExhaustionBehavior: 'AutoPause' // pause instead of billing when the monthly allowance is used
    requestedBackupStorageRedundancy: 'Local'
  }
}

resource plan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: 'asp-${namePrefix}-${suffix}'
  location: location
  kind: 'linux'
  sku: {
    name: 'F1'
    tier: 'Free'
  }
  properties: {
    reserved: true // Linux
  }
}

resource webApp 'Microsoft.Web/sites@2024-04-01' = {
  name: webAppName
  location: location
  kind: 'app,linux'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    clientAffinityEnabled: false
    siteConfig: {
      linuxFxVersion: 'DOTNETCORE|10.0'
      alwaysOn: false // not available on F1
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      http20Enabled: true
      appSettings: [
        { name: 'Entra__TenantId', value: tenantId }
        { name: 'Entra__ClientId', value: apiClientId }
        { name: 'Approval__FinanceThreshold', value: string(financeThreshold) }
        { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsights.properties.ConnectionString }
      ]
      connectionStrings: [
        {
          name: 'Sql'
          type: 'SQLAzure'
          // "Active Directory Default" picks up the system-assigned managed identity in App Service.
          connectionString: 'Server=tcp:${sqlServer.properties.fullyQualifiedDomainName},1433;Database=${databaseName};Authentication=Active Directory Default;Encrypt=True;Connect Timeout=60'
        }
      ]
    }
  }
}

resource basicPublishingFtp 'Microsoft.Web/sites/basicPublishingCredentialsPolicies@2024-04-01' = {
  parent: webApp
  name: 'ftp'
  properties: { allow: false }
}

resource basicPublishingScm 'Microsoft.Web/sites/basicPublishingCredentialsPolicies@2024-04-01' = {
  parent: webApp
  name: 'scm'
  properties: { allow: false }
}

output webAppName string = webAppName
output webAppHostName string = webApp.properties.defaultHostName
output webAppPrincipalId string = webApp.identity.principalId
output sqlServerFqdn string = sqlServer.properties.fullyQualifiedDomainName
output databaseName string = databaseName
