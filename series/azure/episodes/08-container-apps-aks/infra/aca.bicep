// Episode 8, main demo: the orders API on Azure Container Apps (Consumption plan).
//  - ACR Basic, admin user off. The app pulls with a user-assigned managed identity (AcrPull), no registry password
//  - Workload profiles environment, Consumption profile: billed per second while replicas run, scale to zero
//  - Multiple revision mode: v1 and v2 side by side, traffic split by weight
//  - HTTP probes on the app's own endpoints, HTTP scale rule, 0..3 replicas
// Two phases (infra/deploy-aca.sh): deployApp=false creates registry + environment, the image is pushed, then
// deployApp=true creates the app. The app can't be created before its image exists.

targetScope = 'resourceGroup'

param location string = resourceGroup().location

@minLength(3)
@maxLength(10)
param prefix string = 'orders'

@description('Object ID of the person who pushes images (gets AcrPush on the registry).')
param pusherObjectId string

@allowed(['User', 'Group', 'ServicePrincipal'])
param pusherPrincipalType string = 'User'

@description('Create the container app (phase 2). False on the first run, before an image exists.')
param deployApp bool = false

@description('Image tag in the registry, e.g. 1.0.0.')
param imageTag string = '1.0.0'

@description('Revision suffix: lowercase letters, digits and hyphens, e.g. v1-0-0.')
param revisionSuffix string = 'v1-0-0'

@description('Concurrent requests per replica before another replica is added.')
param concurrentRequests int = 20

param maxReplicas int = 3

param tags object = {
  workload: 'contoso-orders'
  environment: 'lab'
}

var token = toLower(uniqueString(subscription().id, resourceGroup().id, prefix))
var acrName = take('acr${prefix}${token}', 50)
var roles = {
  acrPull: '7f951dda-4ed3-4680-a7ca-43fe172d538d'
  acrPush: '8311e382-0749-4cb8-b61a-304f252e45ec'
}

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${prefix}-${token}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
    workspaceCapping: { dailyQuotaGb: 1 } // a lab cost guard
  }
}

resource acr 'Microsoft.ContainerRegistry/registries@2025-04-01' = {
  name: acrName
  location: location
  tags: tags
  sku: { name: 'Basic' }
  properties: {
    adminUserEnabled: false // no registry password: Entra ID for people, managed identity for the app
    policies: {
      // managed-identity pulls by Container Apps need ARM-audience tokens to be accepted (Learn prerequisite)
      azureADAuthenticationAsArmPolicy: { status: 'enabled' }
    }
  }
}

resource pullIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${prefix}-pull'
  location: location
  tags: tags
}

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: acr
  name: guid(acr.id, pullIdentity.id, roles.acrPull)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.acrPull)
    principalId: pullIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource acrPush 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: acr
  name: guid(acr.id, pusherObjectId, roles.acrPush)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.acrPush)
    principalId: pusherObjectId
    principalType: pusherPrincipalType
  }
}

resource env 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-${prefix}-${token}'
  location: location
  tags: tags
  properties: {
    workloadProfiles: [
      { name: 'Consumption', workloadProfileType: 'Consumption' }
    ]
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
  }
}

resource app 'Microsoft.App/containerApps@2024-03-01' = if (deployApp) {
  name: 'ca-${prefix}-api'
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${pullIdentity.id}': {} }
  }
  properties: {
    environmentId: env.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Multiple'
      ingress: {
        external: true
        targetPort: 8080 // the .NET 8+ images listen on 8080 (ASPNETCORE_HTTP_PORTS)
        transport: 'auto'
        allowInsecure: false
        traffic: [
          { latestRevision: true, weight: 100 }
        ]
      }
      registries: [
        { server: acr.properties.loginServer, identity: pullIdentity.id }
      ]
    }
    template: {
      revisionSuffix: revisionSuffix
      containers: [
        {
          name: 'orders-api'
          image: '${acr.properties.loginServer}/contoso/orders-api:${imageTag}'
          resources: { cpu: json('0.25'), memory: '0.5Gi' }
          probes: [
            { type: 'Startup', httpGet: { path: '/healthz/live', port: 8080 }, periodSeconds: 1, failureThreshold: 30 }
            { type: 'Readiness', httpGet: { path: '/healthz/ready', port: 8080 }, periodSeconds: 5, failureThreshold: 3 }
            { type: 'Liveness', httpGet: { path: '/healthz/live', port: 8080 }, periodSeconds: 10, failureThreshold: 3 }
          ]
        }
      ]
      scale: {
        minReplicas: 0 // scale to zero: no replica, no vCPU/memory charge
        maxReplicas: maxReplicas
        rules: [
          { name: 'http', http: { metadata: { concurrentRequests: string(concurrentRequests) } } }
        ]
      }
    }
  }
  dependsOn: [acrPull]
}

output acrName string = acr.name
output acrLoginServer string = acr.properties.loginServer
output environmentName string = env.name
output appName string = deployApp ? app!.name : ''
output appUrl string = deployApp ? 'https://${app!.properties.configuration.ingress.fqdn}' : ''
