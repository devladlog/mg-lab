using 'main.bicep'

// operatorObjectId: Entra object id of the recording user. Pass it on the command line, never commit a real one:
//   az deployment group create ... -p infra/main.bicepparam -p operatorObjectId=$(az ad signed-in-user show --query id -o tsv)
param prefix = 'mgl18'
param consumerGroupName = 'asa'
