using 'budget.bicep'

param amount = 10
// deploy-budget.sh sets BUDGET_EMAIL; the fallback is a fictional address
param contactEmails = [readEnvironmentVariable('BUDGET_EMAIL', 'alex.demo@contoso.com')]
