// DEVLADLOG Azure #4: the identity side of the contoso orders API, as code (Microsoft Graph Bicep extension).
//   - API app registration: v2.0 access tokens, App ID URI api://{tenantId}/contoso-orders, no secrets or certificates
//   - one delegated scope (Orders.Read) for users, one app role for applications (Orders.ReadWrite.All),
//     one app role for users (Orders.Reader), and the idtyp optional claim so the API can tell app tokens apart
//   - service principal with "assignment required": only assigned users and identities can get a token at all
//   - a user-assigned managed identity for the order processor, granted Orders.ReadWrite.All
targetScope = 'resourceGroup'

extension microsoftGraphV1

@description('Prefix for display names and the unique names of the Entra objects.')
@minLength(3)
param workload string = 'contoso'

param location string = resourceGroup().location

@description('Object IDs of users who may call the API on their own behalf (assigned the Orders.Reader app role).')
param readerPrincipalIds array = []

@description('Object IDs that own the app registration (people, not the deployment identity).')
param ownerObjectIds array = []

param tags object = {
  workload: workload
  environment: 'lab'
  owner: 'platform-team'
}

// Stable IDs: the same GUIDs on every deployment, so redeploying never orphans an assignment.
var ids = {
  readScope: guid(workload, 'orders-api', 'scope', 'Orders.Read')
  writeRole: guid(workload, 'orders-api', 'role', 'Orders.ReadWrite.All')
  readerRole: guid(workload, 'orders-api', 'role', 'Orders.Reader')
}

resource api 'Microsoft.Graph/applications@v1.0' = {
  uniqueName: '${workload}-orders-api'
  displayName: '${workload} orders API'
  signInAudience: 'AzureADMyOrg'
  // Secure pattern without a circular reference to our own appId: api://{tenantId}/{string}
  identifierUris: [
    'api://${tenant().tenantId}/${workload}-orders'
  ]
  api: {
    requestedAccessTokenVersion: 2 // aud = the API's client ID; validate only that
    oauth2PermissionScopes: [
      {
        id: ids.readScope
        value: 'Orders.Read'
        type: 'User'
        isEnabled: true
        adminConsentDisplayName: 'Read orders'
        adminConsentDescription: 'Lets the app read orders on behalf of the signed-in user.'
        userConsentDisplayName: 'Read your orders'
        userConsentDescription: 'Lets the app read orders on your behalf.'
      }
    ]
  }
  appRoles: [
    {
      id: ids.writeRole
      value: 'Orders.ReadWrite.All'
      displayName: 'Read and write all orders'
      description: 'Applications (daemons, managed identities) that process orders.'
      allowedMemberTypes: ['Application']
      isEnabled: true
    }
    {
      id: ids.readerRole
      value: 'Orders.Reader'
      displayName: 'Order reader'
      description: 'People who may call the API to read orders.'
      allowedMemberTypes: ['User']
      isEnabled: true
    }
  ]
  optionalClaims: {
    accessToken: [
      { name: 'idtyp', essential: false } // "app" on app-only tokens
    ]
  }
  owners: {
    relationships: ownerObjectIds
  }
}

resource apiSp 'Microsoft.Graph/servicePrincipals@v1.0' = {
  appId: api.appId
  appRoleAssignmentRequired: true
}

resource processor 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${workload}-order-processor'
  location: location
  tags: tags
}

resource processorCanWrite 'Microsoft.Graph/appRoleAssignedTo@v1.0' = {
  appRoleId: ids.writeRole
  principalId: processor.properties.principalId
  resourceId: apiSp.id
}

resource readers 'Microsoft.Graph/appRoleAssignedTo@v1.0' = [for principalId in readerPrincipalIds: {
  appRoleId: ids.readerRole
  principalId: principalId
  resourceId: apiSp.id
}]

output tenantId string = tenant().tenantId
output apiClientId string = api.appId
output apiAppIdUri string = api.identifierUris[0]
output readScope string = '${api.identifierUris[0]}/Orders.Read'
output processorClientId string = processor.properties.clientId
output processorPrincipalId string = processor.properties.principalId
output processorResourceId string = processor.id
