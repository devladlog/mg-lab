// DEVLADLOG Deep Dive #10: Contoso's finance-review worker on AKS, with Dapr (pub/sub) and KEDA (scale on the
// Service Bus subscription). Lab sizing: Free control plane tier, two small nodes, Dapr without high availability.
targetScope = 'resourceGroup'

@description('Region. West Europe for the lab.')
param location string = resourceGroup().location

@description('Node VM size. Check availability first: az vm list-skus -l westeurope --size Standard_D2s_v5 -o table')
param nodeVmSize string = 'Standard_D2s_v5'

@description('Number of nodes in the one node pool.')
@minValue(1)
@maxValue(3)
param nodeCount int = 2

@description('Kubernetes namespace and service account the worker runs as (the federated credential is bound to this pair).')
param workloadNamespace string = 'contoso-finance'
param workloadServiceAccount string = 'finance-worker'

var token = take(uniqueString(subscription().id, resourceGroup().id), 6)
var sbName = 'sb-mgl10-${token}'
var acrName = 'acrmgl10${token}'
var aksName = 'aks-mgl10'
var topicName = 'purchase-events'
var subscriptionName = 'finance-review' // Dapr consumerID defaults to the app id; KEDA scales on this same name

var roles = {
  serviceBusDataReceiver: '4f6d3b9b-027b-4f4c-9142-0e5a2a2247e0'
  serviceBusDataOwner: '090c5cfd-751d-490a-894a-3ce6f1109419'
  acrPull: '7f951dda-4ed3-4680-a7ca-43fe172d538d'
}

// ---- Service Bus (same shape as episode 7): Standard, Entra only, duplicate detection, label filter ----------
resource serviceBus 'Microsoft.ServiceBus/namespaces@2024-01-01' = {
  name: sbName
  location: location
  sku: { name: 'Standard', tier: 'Standard' }
  properties: {
    disableLocalAuth: true
    minimumTlsVersion: '1.2'
  }

  resource topic 'topics' = {
    name: topicName
    properties: {
      requiresDuplicateDetection: true
      duplicateDetectionHistoryTimeWindow: 'PT10M'
      defaultMessageTimeToLive: 'P1D'
    }

    // Created here, not by Dapr: the sidecar runs with disableEntityManagement, so it needs no rights to create anything.
    resource financeReview 'subscriptions' = {
      name: subscriptionName
      properties: {
        maxDeliveryCount: 5
        lockDuration: 'PT1M' // Dapr's lockDurationInSec applies only when Dapr creates the subscription
        deadLetteringOnMessageExpiration: true
      }

      resource defaultRule 'rules' = {
        name: '$Default'
        properties: {
          filterType: 'CorrelationFilter'
          correlationFilter: { label: 'purchase.high' }
        }
      }
    }
  }
}

// ---- Container registry (images are built in the cloud with az acr build) -------------------------------------
resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  sku: { name: 'Basic' }
  properties: { adminUserEnabled: false }
}

// ---- Identities: one for the worker (receive on the topic), one for KEDA (read the subscription's counts) ----
resource appIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-mgl10-finance-worker'
  location: location
}

resource kedaIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-mgl10-keda-operator'
  location: location
}

// ---- AKS: workload identity + OIDC issuer + KEDA add-on --------------------------------------------------------
resource aks 'Microsoft.ContainerService/managedClusters@2025-01-01' = {
  name: aksName
  location: location
  sku: { name: 'Base', tier: 'Free' }
  identity: { type: 'SystemAssigned' }
  properties: {
    dnsPrefix: aksName
    agentPoolProfiles: [
      {
        name: 'system'
        mode: 'System'
        count: nodeCount
        vmSize: nodeVmSize
        osType: 'Linux'
      }
    ]
    oidcIssuerProfile: { enabled: true }
    securityProfile: { workloadIdentity: { enabled: true } }
    workloadAutoScalerProfile: { keda: { enabled: true } }
  }
}

// The kubelet pulls images from the registry with its own identity: AcrPull, nothing else, no admin user.
resource kubeletPullsImages 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: acr
  name: guid(acr.id, aks.id, roles.acrPull)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.acrPull)
    principalId: aks.properties.identityProfile.kubeletidentity.objectId
    principalType: 'ServicePrincipal'
  }
}

// ---- Dapr extension. HA is the extension default (three replicas of each control plane service): off for the lab ---
resource dapr 'Microsoft.KubernetesConfiguration/extensions@2023-05-01' = {
  name: 'dapr'
  scope: aks
  identity: { type: 'SystemAssigned' }
  properties: {
    extensionType: 'microsoft.dapr'
    autoUpgradeMinorVersion: true
    releaseTrain: 'stable'
    scope: { cluster: { releaseNamespace: 'dapr-system' } }
    configurationSettings: {
      'global.clusterType': 'managedclusters'
      'global.ha.enabled': 'false'
    }
  }
}

// ---- Federated credentials: who may become which identity ------------------------------------------------------
resource workerFederation 'Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials@2023-01-31' = {
  parent: appIdentity
  name: 'finance-worker'
  properties: {
    issuer: aks.properties.oidcIssuerProfile.issuerURL
    subject: 'system:serviceaccount:${workloadNamespace}:${workloadServiceAccount}'
    audiences: ['api://AzureADTokenExchange']
  }
}

resource kedaFederation 'Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials@2023-01-31' = {
  parent: kedaIdentity
  name: 'keda-operator'
  properties: {
    issuer: aks.properties.oidcIssuerProfile.issuerURL
    subject: 'system:serviceaccount:kube-system:keda-operator'
    audiences: ['api://AzureADTokenExchange']
  }
}

// ---- Roles --------------------------------------------------------------------------------------------------------
resource workerReceives 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: serviceBus::topic
  name: guid(serviceBus.id, topicName, appIdentity.id, roles.serviceBusDataReceiver)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.serviceBusDataReceiver)
    principalId: appIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// Learn's KEDA + workload identity tutorial grants Data Owner on the namespace so the scaler can read message counts.
resource kedaReadsCounts 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: serviceBus
  name: guid(serviceBus.id, kedaIdentity.id, roles.serviceBusDataOwner)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.serviceBusDataOwner)
    principalId: kedaIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

output aksName string = aks.name
output acrName string = acr.name
output acrLoginServer string = acr.properties.loginServer
output serviceBusNamespace string = serviceBus.name
output serviceBusFqdn string = '${serviceBus.name}.servicebus.windows.net'
output topicName string = topicName
output subscriptionName string = subscriptionName
output appClientId string = appIdentity.properties.clientId
output kedaClientId string = kedaIdentity.properties.clientId
output workloadNamespace string = workloadNamespace
