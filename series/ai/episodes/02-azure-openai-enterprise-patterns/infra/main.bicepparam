using 'main.bicep'

param prefix = 'mglab-aoai'
param primaryLocation = 'swedencentral'
param secondaryLocation = 'germanywestcentral'
param modelName = 'gpt-5-mini'
param modelVersion = '2025-08-07'
param deploymentSku = 'DataZoneStandard'
param capacityPrimary = 10
param capacitySecondary = 10
param publisherEmail = 'ai-platform@contoso.com'
param teams = ['hr-bot', 'sales-copilot']
