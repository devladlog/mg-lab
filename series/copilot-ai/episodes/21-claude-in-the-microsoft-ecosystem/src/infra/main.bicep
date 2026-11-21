// Claude on Microsoft Foundry (episode 21): Foundry resource + project + one Claude deployment per entry of `deployments`.
// Shape: Learn "Deploy Claude models in Microsoft Foundry using Bicep or Terraform" (Claude on Foundry starter kit) and the
// Azure Verified Module avm/res/cognitive-services/account, whose compiled template puts the Marketplace attestation in
// properties.modelProviderData of Microsoft.CognitiveServices/accounts/deployments (api-version 2026-05-01).
// The attestation values must describe the real organisation that uses Claude. Deploying accepts the Anthropic Marketplace terms.

@description('Foundry resource name. Becomes the custom subdomain (globally unique).')
param accountName string

@description('Project name inside the Foundry resource.')
param projectName string = '${accountName}-proj'

@description('Region. Learn: check model availability per region first (Claude models are not in every region).')
param location string = resourceGroup().location

@description('Legal entity name of the organisation using Claude (modelProviderData.organizationName).')
param organizationName string

@description('Two-letter ISO 3166-1 country code of the organisation (modelProviderData.countryCode).')
@minLength(2)
@maxLength(2)
param countryCode string

@description('Industry accepted by the resource provider (modelProviderData.industry).')
@allowed([ 'education', 'finance', 'government', 'healthcare', 'manufacturing', 'media', 'other', 'retail', 'technology' ])
param industry string

@description('One entry per Claude deployment. `name` is what the Messages API receives as `model`; `version` is optional (take it from the catalogue for the hosting option you want).')
param deployments array

@description('Capacity in thousands of tokens per minute (Learn: capacity 25 = 25,000 TPM).')
param capacity int = 25

@description('Entra object id that may call the models (Cognitive Services User). Empty = no role assignment.')
param principalId string = ''

@description('Entra ID only (no API keys). Claude Mythos models support Entra ID only.')
param disableLocalAuth bool = true

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: accountName
  location: location
  kind: 'AIServices'
  sku: { name: 'S0' }
  identity: { type: 'SystemAssigned' }
  properties: {
    allowProjectManagement: true
    customSubDomainName: accountName
    disableLocalAuth: disableLocalAuth
    publicNetworkAccess: 'Enabled'
  }
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  parent: account
  name: projectName
  location: location
  identity: { type: 'SystemAssigned' }
  properties: {}
}

// Deployments on one account are created one after the other.
@batchSize(1)
resource claude 'Microsoft.CognitiveServices/accounts/deployments@2026-05-01' = [for d in deployments: {
  parent: account
  name: d.name
  sku: { name: 'GlobalStandard', capacity: capacity }
  properties: {
    model: {
      format: 'Anthropic'
      name: d.model
      version: d.?version // omitted when not set
    }
    #disable-next-line BCP037 // modelProviderData is not in the published type for this API version; the AVM module sends it the same way
    modelProviderData: {
      organizationName: organizationName
      countryCode: countryCode
      industry: industry
    }
  }
}]

// Cognitive Services User: the role Learn's starter kit assigns for keyless model invocation.
var cognitiveServicesUser = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'a97b65f3-24c7-4388-baec-2e87135dc908')
resource invoke 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  scope: account
  name: guid(account.id, principalId, cognitiveServicesUser)
  properties: {
    principalId: principalId
    principalType: 'User'
    roleDefinitionId: cognitiveServicesUser
  }
}

output resourceName string = account.name
output baseUrl string = 'https://${accountName}.services.ai.azure.com/anthropic'
output projectEndpoint string = 'https://${accountName}.services.ai.azure.com/api/projects/${projectName}'
output deploymentNames array = [for d in deployments: d.name]
