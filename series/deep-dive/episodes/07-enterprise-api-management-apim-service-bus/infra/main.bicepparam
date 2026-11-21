using './main.bicep'

// Fictional lab values. apiClientId comes from apim/entra/New-GatewayApps.ps1 (zero GUID here on purpose).
param location = 'westeurope'
param publisherEmail = 'labadmin@contoso.com'
param apiClientId = '00000000-0000-0000-0000-000000000000'
param receiverPrincipalId = ''
param duplicateDetectionWindow = 'PT10M'
