using './main.bicep'

param accountName = 'mglabfoundry21'
// Attestation: describe the real organisation that uses Claude (see Learn, "Terms of use").
param organizationName = 'Momento Galático Unipessoal'
param countryCode = 'PT'
param industry = 'technology'
// Deployment names are free. Model ids come from the Learn "Claude models in Microsoft Foundry" table (Hosted on Azure: GA).
// Add `version` only after reading it from the catalogue / account model list for the hosting option you want.
param deployments = [
  { name: 'claude-sonnet-5-5', model: 'claude-sonnet-5-5' }
  { name: 'claude-haiku-5-5', model: 'claude-haiku-5-5' }
]
param capacity = 25
