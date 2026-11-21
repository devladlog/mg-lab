// A monthly budget for the lab's workloads, filtered by the workload tag that episode 2's policy
// requires. Budgets notify; they never stop or delete anything. Cost data arrives 8-24 hours late
// and budgets are evaluated against it every 24 hours, so this is a daily safety net, not a brake.

targetScope = 'subscription'

@description('Monthly amount, in the billing currency of the subscription.')
param amount int = 10

@description('Workload tag values this budget tracks (episodes 1, 2-3 and 5).')
param workloads array = [
  'order-intake'
  'contoso'
  'contoso-orders'
]

@description('Up to five e-mail addresses. Passed at deploy time, never committed.')
@minLength(1)
@maxLength(5)
param contactEmails array

@description('Budgets start on the first day of a month: default = the current month.')
param startDate string = utcNow('yyyy-MM-01')

param budgetName string = 'budget-contoso-lab'

resource budget 'Microsoft.Consumption/budgets@2023-11-01' = {
  name: budgetName
  properties: {
    category: 'Cost'
    amount: amount
    timeGrain: 'Monthly'
    timePeriod: {
      startDate: startDate // no endDate: the API defaults it to ten years after the start
    }
    filter: {
      tags: {
        name: 'workload'
        operator: 'In'
        values: workloads
      }
    }
    notifications: {
      actual50: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 50
        thresholdType: 'Actual'
        contactEmails: contactEmails
      }
      actual90: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 90
        thresholdType: 'Actual'
        contactEmails: contactEmails
      }
      forecast100: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 100
        thresholdType: 'Forecasted' // warns before the month is over
        contactEmails: contactEmails
      }
    }
  }
}

output budgetId string = budget.id
