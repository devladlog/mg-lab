// Contoso orders API: where the pipeline deploys, and the identity it deploys with.
// One resource group, no secrets anywhere:
//   - App Service plan (Linux) + Web App for Containers, pulling the image from GHCR (public package)
//   - a user-assigned managed identity that trusts ONE GitHub environment (federated credential, OIDC)
//   - Website Contributor for that identity on this resource group only (can't assign roles, can't touch plans)
//
//   az deployment group create -g rg-mglab-devtools-05 -f infra/main.bicep \
//     -p appName=<unique> githubSubject="$(python3 tools/oidc_subject.py ...)"

@description('Globally unique web app name (becomes <appName>.azurewebsites.net).')
@minLength(2)
@maxLength(60)
param appName string

@description('Exact sub claim of the GitHub job that deploys, e.g. repo:<owner>@<ownerId>/<repo>@<repoId>:environment:production (tools/oidc_subject.py prints it).')
param githubSubject string

@description('Image the site starts with, until the first pipeline run replaces it.')
param initialImage string = 'mcr.microsoft.com/dotnet/samples:aspnetapp'

param location string = resourceGroup().location

@allowed(['B1', 'B2', 'S1', 'P0v3'])
param skuName string = 'B1'

var websiteContributor = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'de139f84-1756-47ae-9be6-808fbbe84772')

resource plan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: 'asp-${appName}'
  location: location
  kind: 'linux'
  sku: { name: skuName }
  properties: { reserved: true }   // reserved = Linux
}

resource site 'Microsoft.Web/sites@2024-04-01' = {
  name: appName
  location: location
  kind: 'app,linux,container'
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'DOCKER|${initialImage}'
      alwaysOn: true
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      healthCheckPath: '/healthz'
      appSettings: [
        { name: 'WEBSITES_PORT', value: '8080' }                       // the .NET images listen on 8080
        { name: 'WEBSITES_ENABLE_APP_SERVICE_STORAGE', value: 'false' } // no /home share: SQLite stays in /data
      ]
    }
  }
}

// OIDC deploys need no publishing credentials: switch basic auth off for FTP and SCM.
resource ftp 'Microsoft.Web/sites/basicPublishingCredentialsPolicies@2024-04-01' = {
  parent: site
  name: 'ftp'
  properties: { allow: false }
}

resource scm 'Microsoft.Web/sites/basicPublishingCredentialsPolicies@2024-04-01' = {
  parent: site
  name: 'scm'
  properties: { allow: false }
}

resource deployer 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${appName}-deploy'
  location: location
}

resource github 'Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials@2023-01-31' = {
  parent: deployer
  name: 'github-production'
  properties: {
    issuer: 'https://token.actions.githubusercontent.com'
    subject: githubSubject              // matched exactly and case-sensitively, no wildcards
    audiences: ['api://AzureADTokenExchange']
  }
}

resource deployerCanDeploy 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, deployer.id, websiteContributor)
  properties: {
    roleDefinitionId: websiteContributor
    principalId: deployer.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// Values for the GitHub "production" environment (secrets AZURE_CLIENT_ID, AZURE_TENANT_ID,
// AZURE_SUBSCRIPTION_ID; variables AZURE_WEBAPP_NAME, AZURE_RESOURCE_GROUP).
output AZURE_CLIENT_ID string = deployer.properties.clientId
output AZURE_TENANT_ID string = deployer.properties.tenantId
output AZURE_SUBSCRIPTION_ID string = subscription().subscriptionId
output AZURE_WEBAPP_NAME string = site.name
output AZURE_RESOURCE_GROUP string = resourceGroup().name
output url string = 'https://${site.properties.defaultHostName}'
