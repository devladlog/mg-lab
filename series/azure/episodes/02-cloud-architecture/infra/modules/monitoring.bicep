// One Log Analytics workspace for the workload: every resource sends its logs here.
param location string
param name string
param tags object
param retentionInDays int

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${name}'
  location: location
  tags: tags
  properties: {
    retentionInDays: retentionInDays
    sku: { name: 'PerGB2018' }
  }
}

output workspaceId string = logs.id
