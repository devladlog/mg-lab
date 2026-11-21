using './main.bicep'

// Fictional values. Put the real ones on the command line at deploy time, don't commit them.
param location = 'westeurope'
param namePrefix = 'purchreq'
param apiClientId = '00000000-0000-0000-0000-0000000000a1'
param sqlAdminLogin = 'SQL Admins - Purchase Requests'
param sqlAdminObjectId = '00000000-0000-0000-0000-0000000000b1'
param sqlAdminPrincipalType = 'Group'
param financeThreshold = 5000
