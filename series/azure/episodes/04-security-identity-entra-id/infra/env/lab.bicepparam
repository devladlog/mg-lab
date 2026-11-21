using '../identity.bicep'

param workload = 'contoso'
// Filled in by deploy.sh with the signed-in user's object ID (az ad signed-in-user show), never committed.
param readerPrincipalIds = []
param ownerObjectIds = []
