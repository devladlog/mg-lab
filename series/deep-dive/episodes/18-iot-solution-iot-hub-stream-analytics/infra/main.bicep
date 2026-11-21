// DEVLADLOG Deep Dive #18: IoT Hub (free tier) -> Stream Analytics -> Blob storage.
// Scope: one resource group (rg-mglab-deep-dive-18). Nothing here is secret: the one key Stream Analytics needs
// (IoT Hub input, no managed identity support) is read inside the template and never output.
targetScope = 'resourceGroup'

@description('Region. The free IoT Hub (one per subscription) and the job live together.')
param location string = resourceGroup().location

@description('Short prefix for names; a hash of the resource group id is added.')
@minLength(3)
@maxLength(8)
param prefix string = 'mgl18'

@description('Entra object id of the recording user, to browse the output containers (Storage Blob Data Reader). Empty skips it.')
param operatorObjectId string = ''

@description('Name of the consumer group the job reads with (Learn: one consumer group per Stream Analytics job).')
param consumerGroupName string = 'asa'

var suffix = take(uniqueString(resourceGroup().id), 6)
var hubName = 'iot-${prefix}-${suffix}'
var storageName = toLower('st${prefix}${suffix}')
var jobName = 'asa-${prefix}-${suffix}'
var inputAlias = 'telemetry'
var outputAliases = [ 'aggregates', 'alerts' ]
var blobDataContributor = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
var blobDataReader = '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1'

resource hub 'Microsoft.Devices/IotHubs@2023-06-30' = {
  name: hubName
  location: location
  sku: {
    name: 'F1' // free: 500 devices, 8,000 messages per day, one free hub per subscription
    capacity: 1
  }
  properties: {
    minTlsVersion: '1.2'
    eventHubEndpoints: {
      events: {
        retentionTimeInDays: 1
        partitionCount: 2
      }
    }
  }
}

resource consumerGroup 'Microsoft.Devices/IotHubs/eventHubEndpoints/ConsumerGroups@2023-06-30' = {
  name: '${hub.name}/events/${consumerGroupName}'
  properties: {
    name: consumerGroupName
  }
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false // the job writes with its managed identity
    supportsHttpsTrafficOnly: true
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource containers 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = [for alias in outputAliases: {
  parent: blobService
  name: alias
  properties: { publicAccess: 'None' }
}]

resource job 'Microsoft.StreamAnalytics/streamingjobs@2021-10-01-preview' = {
  name: jobName
  location: location
  identity: { type: 'SystemAssigned' }
  sku: { name: 'Standard' }
  properties: {
    jobType: 'Cloud'
    dataLocale: 'en-US'
    compatibilityLevel: '1.2'
    outputErrorPolicy: 'Drop'
    eventsOutOfOrderPolicy: 'Adjust'
    eventsOutOfOrderMaxDelayInSeconds: 5
    eventsLateArrivalMaxDelayInSeconds: 60
    contentStoragePolicy: 'SystemAccount'
  }
}

resource streamInput 'Microsoft.StreamAnalytics/streamingjobs/inputs@2021-10-01-preview' = {
  parent: job
  name: inputAlias
  properties: {
    type: 'Stream'
    datasource: {
      type: 'Microsoft.Devices/IotHubs'
      properties: {
        iotHubNamespace: hub.name
        sharedAccessPolicyName: 'service'
        sharedAccessPolicyKey: filter(hub.listKeys().value, policy => policy.keyName == 'service')[0].primaryKey
        consumerGroupName: consumerGroupName
        endpoint: 'messages/events'
      }
    }
    serialization: {
      type: 'Json'
      properties: { encoding: 'UTF8' }
    }
  }
  dependsOn: [ consumerGroup ]
}

// Least privilege: the job's identity may write to its own two containers only.
resource jobCanWrite 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for (alias, i) in outputAliases: {
  name: guid(storage.id, alias, job.id, blobDataContributor)
  scope: containers[i]
  properties: {
    principalId: job.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', blobDataContributor)
  }
}]

resource streamOutputs 'Microsoft.StreamAnalytics/streamingjobs/outputs@2021-10-01-preview' = [for (alias, i) in outputAliases: {
  parent: job
  name: alias
  properties: {
    datasource: {
      type: 'Microsoft.Storage/Blob'
      properties: {
        storageAccounts: [ { accountName: storage.name } ]
        container: alias
        pathPattern: '{date}'
        dateFormat: 'yyyy/MM/dd'
        timeFormat: 'HH'
        authenticationMode: 'Msi'
      }
    }
    serialization: {
      type: 'Json'
      properties: {
        encoding: 'UTF8'
        format: 'LineSeparated'
      }
    }
  }
  dependsOn: [ jobCanWrite ]
}]

// The query lives in one file (asa/coldroom-telemetry.asaql): the unit tests run that same file.
resource transformation 'Microsoft.StreamAnalytics/streamingjobs/transformations@2021-10-01-preview' = {
  parent: job
  name: 'Transformation'
  properties: {
    streamingUnits: 1
    query: loadTextContent('../asa/coldroom-telemetry.asaql')
  }
  dependsOn: [ streamInput, streamOutputs ]
}

resource operatorCanRead 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(operatorObjectId)) {
  name: guid(storage.id, operatorObjectId, blobDataReader)
  scope: storage
  properties: {
    principalId: operatorObjectId
    principalType: 'User'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', blobDataReader)
  }
}

output hubName string = hub.name
output hubHostName string = hub.properties.hostName
output storageAccountName string = storage.name
output jobName string = job.name
