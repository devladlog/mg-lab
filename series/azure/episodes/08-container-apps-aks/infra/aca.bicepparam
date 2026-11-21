using 'aca.bicep'

// deploy-aca.sh sets these; nothing personal is committed
param pusherObjectId = readEnvironmentVariable('PUSHER_OBJECT_ID')
param deployApp = bool(readEnvironmentVariable('DEPLOY_APP', 'false'))
param imageTag = readEnvironmentVariable('IMAGE_TAG', '1.0.0')
param revisionSuffix = readEnvironmentVariable('REVISION_SUFFIX', 'v1-0-0')
