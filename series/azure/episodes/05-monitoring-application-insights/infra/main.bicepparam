using 'main.bicep'

param prefix = 'orders'
// alertEmail has no default on purpose: deploy.sh passes it (ALERT_EMAIL), so no address is committed
param alertEmail = readEnvironmentVariable('ALERT_EMAIL', 'alex.demo@contoso.com')
param dailyCapGb = 1
