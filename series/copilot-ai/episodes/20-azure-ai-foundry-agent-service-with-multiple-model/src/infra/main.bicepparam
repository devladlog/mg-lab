using './main.bicep'

param accountName = 'mglabfoundry20'
// Add a second and third deployment from non-OpenAI models you can actually deploy in your region and quota
// (Format/Name/Version from Get-AzCognitiveServicesAccountModel). Left at one entry so the file deploys as is.
param deployments = [
  {
    name: 'gpt-4.1-mini'
    format: 'OpenAI'
    model: 'gpt-4.1-mini'
    version: '2025-04-14'
    sku: 'GlobalStandard'
    capacity: 1
  }
]
