using './main.bicep'

// Fictional lab values. siteId, list IDs and the provisioning job come from Grant-OnboardingAccess.ps1 and the
// API-driven provisioning app (Provisioning > View technical information): second deployment, see demo.md.
param location = 'westeurope'
param upnDomain = 'contoso.com'
param schedule = '0 */5 * * * *'
param siteId = ''
param requestsListId = ''
param tasksListId = ''
param provisioningServicePrincipalId = ''
param provisioningJobId = ''
