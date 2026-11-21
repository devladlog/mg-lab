using 'main.bicep'

param sourceLocation = 'westeurope'
param drLocation = 'northeurope'
param episode = '17'
// adminPassword is deliberately absent: pass it at deployment time (az deployment sub create ... --parameters adminPassword=<prompted>)
param adminPassword = readEnvironmentVariable('MGLAB_VM_ADMIN_PASSWORD', '')
