using 'main.bicep'

param location = 'swedencentral'
// app registration "HR Copilot API" and the person running the ingestion (fictional zero ids; set yours)
param apiClientId = '00000000-0000-0000-0000-000000000000'
param ingestPrincipalId = '00000000-0000-0000-0000-000000000000'
param ingestPrincipalType = 'User'
param chatModel = 'gpt-5.4-mini'
param chatModelVersion = '2026-03-17'
param chatSku = 'DataZoneStandard'
