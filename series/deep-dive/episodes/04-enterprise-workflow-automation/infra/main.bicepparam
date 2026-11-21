using './main.bicep'

// Fictional lab users. The demo shortens the deadline so the escalation happens on camera.
param location = 'westeurope'
param managerEmail = 'sam.demo@contoso.com'
param financeEmail = 'jordan.demo@contoso.com'
param escalationEmail = 'riley.demo@contoso.com'
param financeThreshold = 5000
param stageTimeoutMinutes = 2880
param flowAudience = ''
param durableAlwaysReady = 0
