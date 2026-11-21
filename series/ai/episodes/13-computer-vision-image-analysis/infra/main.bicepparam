using 'main.bicep'

param prefix = 'mglab-vis'
param location = 'westeurope'
param skuName = 'F0'
param developerPrincipalId = '00000000-0000-0000-0000-000000000000' // replace with: az ad signed-in-user show --query id -o tsv
param developerPrincipalType = 'User'
