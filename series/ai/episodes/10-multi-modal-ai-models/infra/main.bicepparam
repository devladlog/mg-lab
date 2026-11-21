using 'main.bicep'

param prefix = 'mglab-mm'
param location = 'swedencentral'
param developerPrincipalId = '00000000-0000-0000-0000-000000000000' // replace with: az ad signed-in-user show --query id -o tsv
param developerPrincipalType = 'User'
