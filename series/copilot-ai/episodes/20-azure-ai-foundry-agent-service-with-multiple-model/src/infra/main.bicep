// Microsoft Foundry resource + project + N model deployments in one resource group (episode 20).
// Shape follows the Foundry quickstart template (microsoft-foundry/foundry-samples, infrastructure-setup-bicep/00-basic):
// an AIServices account with project management enabled, a project, and Microsoft.CognitiveServices/accounts/deployments.
// For models other than OpenAI, take `format`, `model` and `version` from the models your account lists:
//   Get-AzCognitiveServicesAccountModel -ResourceGroupName <rg> -AccountName <account>   (columns Format, Name, Version)

@description('Foundry resource name. Becomes the custom subdomain, so it must be globally unique (lowercase letters, digits, hyphens).')
param accountName string

@description('Project name inside the Foundry resource.')
param projectName string = '${accountName}-proj'

@description('Region. Check model availability for this region first.')
param location string = resourceGroup().location

@description('One entry per model deployment. `name` is the deployment name that agents use as their `model`.')
param deployments array = [
  {
    name: 'gpt-4.1-mini'
    format: 'OpenAI'
    model: 'gpt-4.1-mini'
    version: '2025-04-14'
    sku: 'GlobalStandard'
    capacity: 1
  }
]

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: accountName
  location: location
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    allowProjectManagement: true
    customSubDomainName: accountName
    disableLocalAuth: true // Entra ID only: the code uses DefaultAzureCredential, no API keys
    publicNetworkAccess: 'Enabled'
  }
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  parent: account
  name: projectName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {}
}

// Deployments on one account are created one after the other.
@batchSize(1)
resource modelDeployments 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = [for d in deployments: {
  parent: account
  name: d.name
  sku: {
    name: d.sku
    capacity: d.capacity
  }
  properties: {
    model: {
      format: d.format
      name: d.model
      version: d.version
    }
  }
}]

output projectEndpoint string = 'https://${accountName}.services.ai.azure.com/api/projects/${projectName}'
output projectResourceId string = project.id
output deploymentNames array = [for d in deployments: d.name]
