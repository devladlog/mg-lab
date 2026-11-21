// Orders API on App Service with Application Insights done properly:
// workspace-based, Entra ID-only ingestion, a daily cap, a standard availability test,
// two metric alerts (not affected by sampling) and one log search alert whose KQL lives in
// ../queries/alert-failure-ratio.kql (the same file the unit tests check against the schema).

targetScope = 'resourceGroup'

param location string = resourceGroup().location

@minLength(3)
@maxLength(10)
param prefix string = 'orders'

@description('Who gets the alert e-mails. Passed at deploy time, never committed.')
param alertEmail string

@description('Daily ingestion cap for the workspace, in GB. A last-resort cost guard, not a sampling strategy.')
param dailyCapGb int = 1

@description('Standard test locations. Microsoft recommends at least five; alert at locations - 2 failing.')
param testLocations array = [
  'emea-nl-ams-azr' // West Europe
  'emea-gb-db3-azr' // North Europe
  'emea-fr-pra-edge' // France Central
  'emea-ru-msa-edge' // UK South
  'emea-se-sto-edge' // UK West
]

param tags object = {
  workload: 'contoso-orders'
  environment: 'lab'
}

var token = toLower(uniqueString(subscription().id, resourceGroup().id, prefix))
var appName = 'app-${prefix}-${token}'
var roleName = 'contoso-orders-api' // = service.name in TelemetrySetup.cs = AppRoleName in the queries

var roles = {
  blobDataContributor: 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
  monitoringMetricsPublisher: '3913510d-42f4-4e42-8a64-420c390055eb'
}

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${prefix}-${token}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
    workspaceCapping: { dailyQuotaGb: dailyCapGb }
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${prefix}-${token}'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logs.id
    DisableLocalAuth: true // telemetry needs an Entra token: a leaked connection string can't write
  }
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: take('st${prefix}${token}', 24)
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
  properties: {
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
  }

  resource blobs 'blobServices' = {
    name: 'default'
    resource orders 'containers' = { name: 'orders' }
  }
}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${prefix}-${token}'
  location: location
  tags: tags
}

resource blobRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, identity.id, roles.blobDataContributor)
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.blobDataContributor)
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource telemetryRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(appInsights.id, identity.id, roles.monitoringMetricsPublisher)
  scope: appInsights
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.monitoringMetricsPublisher)
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource plan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: 'plan-${prefix}-${token}'
  location: location
  tags: tags
  kind: 'linux'
  sku: { name: 'B1' }
  properties: { reserved: true }
}

resource app 'Microsoft.Web/sites@2024-04-01' = {
  name: appName
  location: location
  tags: tags
  kind: 'app,linux'
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identity.id}': {} }
  }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    clientAffinityEnabled: false
    siteConfig: {
      linuxFxVersion: 'DOTNETCORE|10.0'
      minTlsVersion: '1.2'
      ftpsState: 'Disabled'
      alwaysOn: true
      healthCheckPath: '/healthz'
      appSettings: [
        { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsights.properties.ConnectionString }
        { name: 'AZURE_CLIENT_ID', value: identity.properties.clientId } // telemetry + blob credential
        { name: 'Orders__BlobContainerUri', value: '${storage.properties.primaryEndpoints.blob}orders' }
        { name: 'Telemetry__TracesPerSecond', value: '5' }
        { name: 'Chaos__FailurePercent', value: '0' } // the demo raises this with az webapp config appsettings set
        { name: 'Chaos__ExtraLatencyMs', value: '0' }
      ]
    }
  }
  dependsOn: [blobRole, telemetryRole]
}

// Standard test (URL ping tests retire on 30 September 2028)
resource availability 'Microsoft.Insights/webtests@2022-06-15' = {
  name: 'webtest-${prefix}-healthz'
  location: location
  tags: union(tags, { 'hidden-link:${appInsights.id}': 'Resource' }) // links the test to the component
  kind: 'standard'
  properties: {
    Name: 'orders-api-healthz'
    SyntheticMonitorId: 'webtest-${prefix}-healthz'
    Kind: 'standard'
    Enabled: true
    Frequency: 300
    Timeout: 30
    RetryEnabled: true
    Locations: [for id in testLocations: { Id: id }]
    Request: {
      RequestUrl: 'https://${app.properties.defaultHostName}/healthz'
      HttpVerb: 'GET'
      ParseDependentRequests: false
    }
    ValidationRules: {
      ExpectedHttpStatusCode: 200
      SSLCheck: true
      SSLCertRemainingLifetimeCheck: 7
    }
  }
}

resource actionGroup 'Microsoft.Insights/actionGroups@2023-01-01' = {
  name: 'ag-${prefix}-oncall'
  location: 'global'
  tags: tags
  properties: {
    groupShortName: 'orders'
    enabled: true
    emailReceivers: [
      { name: 'oncall-email', emailAddress: alertEmail, useCommonAlertSchema: true }
    ]
  }
}

// 1) Availability: X of Y locations failing (Learn: threshold = locations - 2)
resource availabilityAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'alert-${prefix}-availability'
  location: 'global'
  tags: tags
  properties: {
    description: 'healthz fails from at least ${length(testLocations) - 2} of ${length(testLocations)} locations'
    severity: 1
    enabled: true
    scopes: [availability.id, appInsights.id]
    evaluationFrequency: 'PT1M'
    windowSize: 'PT5M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.WebtestLocationAvailabilityCriteria'
      webTestId: availability.id
      componentId: appInsights.id
      failedLocationCount: length(testLocations) - 2
    }
    actions: [{ actionGroupId: actionGroup.id }]
  }
}

// 2) Failed requests: a standard metric, pre-aggregated, so sampling doesn't change the count
resource failedRequestsAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'alert-${prefix}-failed-requests'
  location: 'global'
  tags: tags
  properties: {
    description: 'More than 5 failed requests in 5 minutes'
    severity: 2
    enabled: true
    scopes: [appInsights.id]
    evaluationFrequency: 'PT1M'
    windowSize: 'PT5M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          criterionType: 'StaticThresholdCriterion'
          name: 'failed-requests'
          metricNamespace: 'microsoft.insights/components'
          metricName: 'requests/failed'
          timeAggregation: 'Count'
          operator: 'GreaterThan'
          threshold: 5
        }
      ]
    }
    actions: [{ actionGroupId: actionGroup.id }]
  }
}

// 3) Failure ratio per operation: needs a division, so it's a log search alert on the workspace
resource failureRatioAlert 'Microsoft.Insights/scheduledQueryRules@2023-12-01' = {
  name: 'alert-${prefix}-failure-ratio'
  location: location
  tags: tags
  kind: 'LogAlert'
  properties: {
    displayName: 'Orders API failure ratio above 10 percent'
    description: 'Query: queries/alert-failure-ratio.kql (role ${roleName}, at least 20 requests)'
    severity: 2
    enabled: true
    scopes: [logs.id]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT5M'
    criteria: {
      allOf: [
        {
          query: loadTextContent('../queries/alert-failure-ratio.kql')
          timeAggregation: 'Maximum'
          metricMeasureColumn: 'FailurePercent'
          dimensions: [
            { name: 'OperationName', operator: 'Include', values: ['*'] }
          ]
          operator: 'GreaterThan'
          threshold: 10
          failingPeriods: { numberOfEvaluationPeriods: 1, minFailingPeriodsToAlert: 1 }
        }
      ]
    }
    autoMitigate: true
    actions: { actionGroups: [actionGroup.id] }
  }
}

output appName string = app.name
output appUrl string = 'https://${app.properties.defaultHostName}'
output appInsightsName string = appInsights.name
output workspaceName string = logs.name
