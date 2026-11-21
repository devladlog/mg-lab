using 'main.bicep'

// Read at deploy time (deploy.sh sets them from az ad signed-in-user show and your public IP).
// Nothing personal or secret is committed.
param adminObjectId = readEnvironmentVariable('ADMIN_OBJECT_ID')
param adminLogin = readEnvironmentVariable('ADMIN_LOGIN')
param clientIp = readEnvironmentVariable('CLIENT_IP')
