using 'main.bicep'

// developerPrincipalId is passed on the command line (az ad signed-in-user show --query id -o tsv).
// Leave it empty on the first deployment to see the 403 that Owner alone produces.
param prefix = 'mglab-ai17'
param location = 'westeurope'
