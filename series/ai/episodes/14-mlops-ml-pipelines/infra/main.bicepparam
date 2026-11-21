using 'main.bicep'

param prefix = 'mglab-mlops'
param trainingVmSize = 'Standard_DS3_v2'
param maxNodes = 1
param ciPrincipalId = '' // object ID of the CI identity; empty = none (the lab account is Owner and needs no assignment)
param ciPrincipalType = 'ServicePrincipal'
