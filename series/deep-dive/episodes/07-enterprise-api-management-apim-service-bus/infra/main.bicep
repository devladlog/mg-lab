// DEVLADLOG Deep Dive #7: Azure API Management (Consumption) in front of an Azure Service Bus topic.
// The gateway's system-assigned identity is the ONLY sender (Azure Service Bus Data Sender, scoped to the topic),
// shared access keys are switched off on the namespace, and the policy is loaded from apim/policies.
// Resource group for the demo: rg-mglab-deep-dive-07 (delete it after recording).

@description('Region for all resources.')
param location string = resourceGroup().location

@minLength(3)
param resourceToken string = toLower(uniqueString(subscription().id, resourceGroup().id, location))

@description('Publisher e-mail shown in API Management (a lab address).')
param publisherEmail string
param publisherName string = 'Contoso lab'

@description('Application (client) ID of the "contoso-purchase-gateway" app registration (the API the tokens are issued for).')
param apiClientId string

@description('Object ID of the lab user who runs the worker locally: gets Azure Service Bus Data Receiver on the topic. Empty to skip.')
param receiverPrincipalId string = ''

@description('Duplicate detection window (ISO 8601). Learn: default 10 minutes, minimum 20 seconds, maximum 7 days.')
param duplicateDetectionWindow string = 'PT10M'

var apimName = 'apim-mgl07-${resourceToken}'
var sbName = 'sb-mgl07-${resourceToken}'
var topicName = 'purchase-events'

var roles = {
  serviceBusDataSender: '69a216fc-b8fb-44d8-bc22-1f3c2cd27a39'
  serviceBusDataReceiver: '4f6d3b9b-027b-4f4c-9142-0e5a2a2247e0'
}

// ---- Service Bus: Standard (topics + duplicate detection), Entra-only -----------------------------------------
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
      duplicateDetectionHistoryTimeWindow: duplicateDetectionWindow
      defaultMessageTimeToLive: 'P1D'
    }

    // Everything, for the audit/read model.
    resource allEvents 'subscriptions' = {
      name: 'all-events'
      properties: {
        maxDeliveryCount: 5
        lockDuration: 'PT30S'
        deadLetteringOnMessageExpiration: true
      }
    }

    // Only events the gateway labelled purchase.high. The auto-created $Default rule (true) is replaced.
    resource financeReview 'subscriptions' = {
      name: 'finance-review'
      properties: {
        maxDeliveryCount: 5
        lockDuration: 'PT30S'
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

// ---- API Management: Consumption, system-assigned identity ----------------------------------------------------
resource apim 'Microsoft.ApiManagement/service@2024-05-01' = {
  name: apimName
  location: location
  sku: { name: 'Consumption', capacity: 0 }
  identity: { type: 'SystemAssigned' }
  properties: {
    publisherEmail: publisherEmail
    publisherName: publisherName
  }

  resource nvTenant 'namedValues' = {
    name: 'tenant-id'
    properties: { displayName: 'tenant-id', value: tenant().tenantId }
  }
  resource nvAudience 'namedValues' = {
    name: 'api-client-id'
    properties: { displayName: 'api-client-id', value: apiClientId }
  }
  resource nvNamespace 'namedValues' = {
    name: 'servicebus-namespace'
    properties: { displayName: 'servicebus-namespace', value: serviceBus.name }
  }
  resource nvTopic 'namedValues' = {
    name: 'topic-name'
    properties: { displayName: 'topic-name', value: topicName }
  }

  resource api 'apis' = {
    name: 'purchasing'
    dependsOn: [nvTenant, nvAudience, nvNamespace, nvTopic]
    properties: {
      displayName: 'Contoso purchasing events'
      path: 'purchasing'
      protocols: ['https']
      subscriptionRequired: true
      format: 'openapi+json'
      value: loadTextContent('../apim/openapi/purchase-events.openapi.json')
    }

    resource policy 'policies' = {
      name: 'policy'
      properties: {
        format: 'rawxml'
        value: loadTextContent('../apim/policies/purchase-events.policy.xml')
      }
    }
  }

  // One subscription key for the lab caller, scoped to this API only. Read the key with listSecrets (see demo.md).
  resource labSubscription 'subscriptions' = {
    name: 'lab-caller'
    properties: {
      displayName: 'Lab caller'
      scope: api.id
      state: 'active'
    }
  }
}

// ---- Least privilege on the topic ------------------------------------------------------------------------------
resource gatewayCanSend 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(serviceBus.id, topicName, apim.id, roles.serviceBusDataSender)
  scope: serviceBus::topic
  properties: {
    principalId: apim.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.serviceBusDataSender)
  }
}

resource labCanReceive 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(receiverPrincipalId)) {
  name: guid(serviceBus.id, topicName, receiverPrincipalId, roles.serviceBusDataReceiver)
  scope: serviceBus::topic
  properties: {
    principalId: receiverPrincipalId
    principalType: 'User'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.serviceBusDataReceiver)
  }
}

output apimName string = apim.name
output gatewayUrl string = apim.properties.gatewayUrl
output serviceBusNamespaceFqdn string = '${serviceBus.name}.servicebus.windows.net'
output topicName string = topicName
output gatewayPrincipalId string = apim.identity.principalId
