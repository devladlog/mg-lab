using './main.bicep'

// Fictional values. Put the real ones on the command line at deploy time, don't commit them.
param location = 'westeurope'
param namePrefix = 'saas'
param homeTenantId = '00000000-0000-0000-0000-000000000001'
param apiClientId = '00000000-0000-0000-0000-0000000000a1'
param sqlAdminLogin = 'lab.admin@contoso.example'
param sqlAdminObjectId = '00000000-0000-0000-0000-0000000000b1'
param sqlAdminPrincipalType = 'User'
