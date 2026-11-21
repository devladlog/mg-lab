// DEVLADLOG Deep Dive #11: Contoso purchase requests as a multitenant SaaS.
// One shared stamp: App Service (F1) + one Azure SQL database (free offer) holding every tenant's rows, isolated by
// the tenant filter in the app and by row-level security in the database. Smallest lab footprint, no passwords:
// SQL is Microsoft Entra-only and the web app reaches it with its system-assigned identity.

targetScope = 'resourceGroup'

@description('Region for all resources.')
param location string = resourceGroup().location

@description('Short prefix for resource names.')
@maxLength(12)
param namePrefix string = 'saas'

@description('Tenant ID of the provider (home) Microsoft Entra tenant: the only one whose Platform.Admin role counts.')
param homeTenantId string = tenant().tenantId

@description('Client ID of the multitenant "Contoso SaaS API" app registration.')
param apiClientId string

@description('Display name of the Entra group (or user) that administers the SQL server.')
param sqlAdminLogin string

@description('Object ID of that group or user.')
param sqlAdminObjectId string

@allowed(['Group', 'User'])
param sqlAdminPrincipalType string = 'User'

var suffix = uniqueString(resourceGroup().id)
var webAppName = 'app-${namePrefix}-${suffix}'
var sqlServerName = 'sql-${namePrefix}-${suffix}'
var databaseName = 'tenants'

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
      tenantId: homeTenantId
      principalType: sqlAdminPrincipalType
    }
  }
}

// F1 has no virtual network integration, so the app reaches SQL over the public endpoint.
// This rule admits ANY Azure-hosted client; only Entra identities with a database user get in.
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
        { name: 'Entra__ClientId', value: apiClientId }
        { name: 'Entra__HomeTenantId', value: homeTenantId }
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
output sqlServerFqdn string = sqlServer.properties.fullyQualifiedDomainName
output databaseName string = databaseName
