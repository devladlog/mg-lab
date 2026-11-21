// DEVLADLOG AI #7: AI governance as code for the HR bot's resource group.
//  - Three built-in Azure Policy assignments on the resource group:
//      keyless (Deny), approved models only (Deny), diagnostic logs (AuditIfNotExists)
//  - The HR bot's Azure OpenAI account: keyless, tagged ai-system-id=hr-bot, audit logs to Log Analytics,
//    guardrail policy with prompt shields, gpt-5-mini pinned on an EU data zone deployment
//  - Optionally a "shadow" account (keyless, untagged, no logs) that the evidence pack must catch
//  No model is called in this episode: the accounts cost nothing while idle.

@description('Short prefix for resource names (a unique suffix is appended).')
param prefix string = 'mglab-gov'
param location string = resourceGroup().location
@description('Value of the ai-system-id tag; must match an id in governance/register.yaml.')
param systemId string = 'hr-bot'
@description('Deploy an untagged account to show that the evidence pack finds unregistered AI resources.')
param deployShadowAccount bool = true

@description('Model asset IDs allowed by the approved-models policy (matched with "contains"; Learn: use a trailing slash or a full version ID).')
param allowedAssetIds array = [
  'azureml://registries/azure-openai/models/gpt-5-mini/versions/2025-08-07'
  'azureml://registries/azure-openai/models/text-embedding-3-small/versions/1'
]
param policyName string = 'contoso-hr-strict'
param chatModel string = 'gpt-5-mini'
param chatVersion string = '2025-08-07'
@allowed(['DataZoneStandard', 'Standard', 'GlobalStandard'])
param chatSku string = 'DataZoneStandard'
param chatCapacity int = 10

var suffix = take(uniqueString(resourceGroup().id), 6)
var tags = { 'ai-system-id': systemId, owner: 'Alex Demo', 'data-classification': 'confidential' }
var builtIn = {
  keyless: '71ef260a-8f18-47b7-abcb-62d0673d94dc' // Azure AI Services resources should have key access disabled
  approvedModels: 'aafe3651-cb78-4f68-9f81-e7e41509110f' // Foundry model deployments should only use approved models
  diagnosticLogs: '1b4d1c4e-934c-4703-944c-27c82c06bebb' // Diagnostic logs in Azure AI services resources should be enabled
}
var contentFilters = [
  { name: 'Hate', severityThreshold: 'Medium', blocking: true, enabled: true, source: 'Prompt' }
  { name: 'Sexual', severityThreshold: 'Medium', blocking: true, enabled: true, source: 'Prompt' }
  { name: 'Violence', severityThreshold: 'Medium', blocking: true, enabled: true, source: 'Prompt' }
  { name: 'Selfharm', severityThreshold: 'Medium', blocking: true, enabled: true, source: 'Prompt' }
  { name: 'Jailbreak', blocking: true, enabled: true, source: 'Prompt' }
  { name: 'Indirect Attack', blocking: true, enabled: true, source: 'Prompt' }
  { name: 'Hate', severityThreshold: 'Medium', blocking: true, enabled: true, source: 'Completion' }
  { name: 'Sexual', severityThreshold: 'Medium', blocking: true, enabled: true, source: 'Completion' }
  { name: 'Violence', severityThreshold: 'Medium', blocking: true, enabled: true, source: 'Completion' }
  { name: 'Selfharm', severityThreshold: 'Medium', blocking: true, enabled: true, source: 'Completion' }
  { name: 'Protected Material Text', blocking: true, enabled: true, source: 'Completion' }
]

// ---------- Azure Policy: guardrails the platform enforces before any code runs ----------
resource keylessAssignment 'Microsoft.Authorization/policyAssignments@2024-04-01' = {
  name: 'ai-keyless-deny'
  properties: {
    displayName: 'AI governance: Azure AI resources must be keyless'
    policyDefinitionId: tenantResourceId('Microsoft.Authorization/policyDefinitions', builtIn.keyless)
    enforcementMode: 'Default'
    parameters: { effect: { value: 'Deny' } }
    nonComplianceMessages: [
      { message: 'Contoso AI governance: create Azure AI resources with disableLocalAuth=true (Entra ID only).' }
    ]
  }
}

resource approvedModelsAssignment 'Microsoft.Authorization/policyAssignments@2024-04-01' = {
  name: 'ai-approved-models-deny'
  properties: {
    displayName: 'AI governance: only approved models and versions'
    policyDefinitionId: tenantResourceId('Microsoft.Authorization/policyDefinitions', builtIn.approvedModels)
    enforcementMode: 'Default'
    parameters: {
      effect: { value: 'Deny' }
      allowedPublishers: { value: [] } // empty: approval by exact asset ID only
      allowedAssetIds: { value: allowedAssetIds }
    }
    nonComplianceMessages: [
      { message: 'Contoso AI governance: this model is not in the approved list. Ask the AI governance board.' }
    ]
  }
}

resource diagnosticLogsAssignment 'Microsoft.Authorization/policyAssignments@2024-04-01' = {
  name: 'ai-diagnostic-logs-audit'
  properties: {
    displayName: 'AI governance: Azure AI resources must send diagnostic logs'
    policyDefinitionId: tenantResourceId('Microsoft.Authorization/policyDefinitions', builtIn.diagnosticLogs)
    enforcementMode: 'Default'
    parameters: { effect: { value: 'AuditIfNotExists' } }
  }
}

// ---------- The HR bot's resources: compliant by construction ----------
resource law 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${prefix}-law-${suffix}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource aoai 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: '${prefix}-aoai-${suffix}'
  location: location
  kind: 'OpenAI'
  sku: { name: 'S0' }
  tags: tags
  properties: {
    customSubDomainName: '${prefix}-aoai-${suffix}'
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
  }
}

resource aoaiLogs 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'to-log-analytics'
  scope: aoai
  properties: {
    workspaceId: law.id
    logs: [
      { category: 'Audit', enabled: true }
      { category: 'RequestResponse', enabled: true }
      { category: 'AzureOpenAIRequestUsage', enabled: true }
    ]
    metrics: [{ category: 'AllMetrics', enabled: true }]
  }
}

resource guardrail 'Microsoft.CognitiveServices/accounts/raiPolicies@2025-06-01' = {
  parent: aoai
  name: policyName
  properties: {
    mode: 'Default'
    basePolicyName: 'Microsoft.DefaultV2'
    contentFilters: contentFilters
  }
}

resource chat 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: aoai
  name: 'chat'
  sku: { name: chatSku, capacity: chatCapacity }
  properties: {
    model: { format: 'OpenAI', name: chatModel, version: chatVersion }
    versionUpgradeOption: 'NoAutoUpgrade'
    raiPolicyName: guardrail.name
  }
}

// ---------- A resource nobody registered: keyless (so policy allows it) but untagged and without logs ----------
resource shadow 'Microsoft.CognitiveServices/accounts@2025-06-01' = if (deployShadowAccount) {
  name: '${prefix}-shadow-${suffix}'
  location: location
  kind: 'OpenAI'
  sku: { name: 'S0' }
  properties: {
    customSubDomainName: '${prefix}-shadow-${suffix}'
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
  }
}

output aoaiName string = aoai.name
output shadowName string = deployShadowAccount ? shadow.name : ''
output workspaceName string = law.name
output policyAssignments array = [keylessAssignment.name, approvedModelsAssignment.name, diagnosticLogsAssignment.name]
