// Guardrails at resource-group scope, deployed BEFORE the workload. Built-in definitions only.
targetScope = 'resourceGroup'

param allowedLocations array
param requiredTagName string = 'workload'

var definitions = {
  allowedLocations: 'e56962a6-4747-49cd-b67b-bf8b01975c4c' // Allowed locations (Deny)
  requireTag: '871b6d14-10aa-478d-b590-94f262ecfa99' // Require a tag on resources (deny)
}

resource locations 'Microsoft.Authorization/policyAssignments@2024-04-01' = {
  name: 'allowed-locations'
  properties: {
    displayName: 'Workload resources only in approved regions'
    policyDefinitionId: tenantResourceId('Microsoft.Authorization/policyDefinitions', definitions.allowedLocations)
    parameters: { listOfAllowedLocations: { value: allowedLocations } }
    nonComplianceMessages: [{ message: 'Deploy only to the approved regions for this workload.' }]
  }
}

resource tag 'Microsoft.Authorization/policyAssignments@2024-04-01' = {
  name: 'require-${requiredTagName}-tag'
  properties: {
    displayName: 'Every resource carries a ${requiredTagName} tag'
    policyDefinitionId: tenantResourceId('Microsoft.Authorization/policyDefinitions', definitions.requireTag)
    parameters: { tagName: { value: requiredTagName } }
    nonComplianceMessages: [{ message: 'Add the ${requiredTagName} tag (cost and ownership reporting).' }]
  }
}

output assignmentIds array = [locations.id, tag.id]
