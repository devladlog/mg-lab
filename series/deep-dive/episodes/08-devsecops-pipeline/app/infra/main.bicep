// DEVLADLOG Deep Dive #8: the Azure side of the secure pipeline.
//  - Azure Container Registry (Basic): admin user OFF (anonymous pull is off by default and is not set), so only Entra identities can push or pull
//  - a "deploy" user-assigned identity trusted by ONE GitHub environment (federated credential, no secret anywhere)
//    with AcrPush on the registry and Contributor on the one Container App only
//  - a "pull" user-assigned identity with AcrPull, used by the Container App to pull the image
//  - Log Analytics, a Container Apps environment (Consumption) and the Container App (scale to zero)
// Resource group for the demo: rg-mglab-deep-dive-08 (delete it after recording).

@description('Region for all resources.')
param location string = resourceGroup().location

@minLength(3)
param resourceToken string = toLower(uniqueString(subscription().id, resourceGroup().id, location))

@description('GitHub organisation or user that owns the throwaway demo repository (fictional in the repo: contoso-demo).')
param githubOwner string

@description('Throwaway demo repository name.')
param githubRepo string = 'purchase-status'

@description('GitHub environment that is allowed to sign in to Azure. It is part of the federated credential subject.')
param githubEnvironment string = 'prod-lab'

@description('Image the Container App starts with, before the pipeline deploys its own digest.')
param bootstrapImage string = 'mcr.microsoft.com/k8se/quickstart:latest'

var acrName = 'acrmgl08${resourceToken}'
var appName = 'ca-mgl08-purchase-status'
var envName = 'cae-mgl08-${resourceToken}'
var logName = 'log-mgl08-${resourceToken}'

// Built-in roles (Learn: Azure built-in roles).
var roles = {
  acrPush: '8311e382-0749-4cb8-b61a-304f252e45ec'
  acrPull: '7f951dda-4ed3-4680-a7ca-43fe172d538d'
  contributor: 'b24988ac-6180-42a0-ab88-20f7382dd24c'
}

// ---- Registry ---------------------------------------------------------------------------------------------------
resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  sku: { name: 'Basic' }
  properties: {
    adminUserEnabled: false
  }
}

// ---- Identities --------------------------------------------------------------------------------------------------
resource deployIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-mgl08-deploy'
  location: location
}

// Only a job that runs in the GitHub environment below can exchange its OIDC token for this identity.
resource deployFederation 'Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials@2023-01-31' = {
  parent: deployIdentity
  name: 'github-${githubEnvironment}'
  properties: {
    issuer: 'https://token.actions.githubusercontent.com'
    subject: 'repo:${githubOwner}/${githubRepo}:environment:${githubEnvironment}'
    audiences: [ 'api://AzureADTokenExchange' ]
  }
}

resource pullIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-mgl08-pull'
  location: location
}

// ---- Role assignments --------------------------------------------------------------------------------------------
resource deployPush 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, deployIdentity.id, roles.acrPush)
  scope: acr
  properties: {
    principalId: deployIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.acrPush)
  }
}

resource appPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, pullIdentity.id, roles.acrPull)
  scope: acr
  properties: {
    principalId: pullIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.acrPull)
  }
}

// Contributor on the Container App ONLY (not the resource group): enough for "az containerapp update".
resource deployContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(app.id, deployIdentity.id, roles.contributor)
  scope: app
  properties: {
    principalId: deployIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.contributor)
  }
}

// ---- Runtime -----------------------------------------------------------------------------------------------------
resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: logName
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource env 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: envName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
  }
}

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: appName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${pullIdentity.id}': {} }
  }
  properties: {
    managedEnvironmentId: env.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8080
        allowInsecure: false
      }
      registries: [
        {
          server: acr.properties.loginServer
          identity: pullIdentity.id
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'purchase-status'
          image: bootstrapImage
          resources: { cpu: json('0.25'), memory: '0.5Gi' }
        }
      ]
      scale: { minReplicas: 0, maxReplicas: 1 }
    }
  }
  dependsOn: [ appPull ]
}

output acrName string = acr.name
output acrLoginServer string = acr.properties.loginServer
output containerAppName string = app.name
output containerAppFqdn string = app.properties.configuration.ingress.fqdn
@description('Client ID of the deploy identity: this is the AZURE_CLIENT_ID of the GitHub environment (an identifier, not a secret).')
output deployClientId string = deployIdentity.properties.clientId
output tenantId string = subscription().tenantId
