# Request bodies generated offline from governance.json

Produced by `./Invoke-IdentityGovernance.ps1 -Preview -Now 2026-11-20T09:30:00Z -StartDate 2026-12-01` (no tenant).

```text
# PIM eligibility: Alex Demo / Groups Administrator
{
  "action": "adminAssign",
  "justification": "Owns the Microsoft 365 groups lifecycle (expiration, restore)",
  "roleDefinitionId": "fdd7a751-b60b-444a-984c-02652fe8fa1c",
  "directoryScopeId": "/",
  "principalId": "00000000-0000-0000-0000-000000000101",
  "scheduleInfo": {
    "startDateTime": "2026-11-20T09:30:00Z",
    "expiration": {
      "type": "afterDateTime",
      "endDateTime": "2027-05-19T09:30:00Z"
    }
  }
}
# Guest access review
{
  "displayName": "Quarterly review - guests in Microsoft 365 groups",
  "scope": {
    "@odata.type": "#microsoft.graph.accessReviewQueryScope",
    "query": "./members/microsoft.graph.user/?$count=true&$filter=(userType eq 'Guest')",
    "queryType": "MicrosoftGraph"
  },
  "instanceEnumerationScope": {
    "@odata.type": "#microsoft.graph.accessReviewQueryScope",
    "query": "/v1.0/groups?$filter=(groupTypes/any(c:c+eq+'Unified'))&$count=true",
    "queryType": "MicrosoftGraph"
  },
  "reviewers": [
    {
      "query": "./owners",
      "queryType": "MicrosoftGraph"
    }
  ],
  "fallbackReviewers": [
    {
      "query": "/users/00000000-0000-0000-0000-000000000101",
      "queryType": "MicrosoftGraph"
    }
  ],
  "settings": {
    "mailNotificationsEnabled": true,
    "reminderNotificationsEnabled": true,
    "justificationRequiredOnApproval": true,
    "defaultDecisionEnabled": true,
    "defaultDecision": "Deny",
    "instanceDurationInDays": 14,
    "autoApplyDecisionsEnabled": true,
    "recommendationsEnabled": true,
    "recommendationLookBackDuration": "P30D",
    "recurrence": {
      "pattern": {
        "type": "absoluteMonthly",
        "interval": 3,
        "month": 0,
        "dayOfMonth": 0,
        "daysOfWeek": [],
        "firstDayOfWeek": "sunday",
        "index": "first"
      },
      "range": {
        "type": "endDate",
        "numberOfOccurrences": 0,
        "recurrenceTimeZone": null,
        "startDate": "2026-12-01",
        "endDate": "2027-12-01"
      }
    },
    "applyActions": [
      {
        "@odata.type": "#microsoft.graph.removeAccessApplyAction"
      }
    ]
  }
}
# Leaver workflow
{
  "category": "leaver",
  "displayName": "Leaver - Sales members on their last day",
  "description": "Revoke sessions, remove group and team memberships, disable the account on employeeLeaveDateTime",
  "isEnabled": true,
  "isSchedulingEnabled": false,
  "executionConditions": {
    "@odata.type": "#microsoft.graph.identityGovernance.triggerAndScopeBasedConditions",
    "scope": {
      "@odata.type": "#microsoft.graph.identityGovernance.ruleBasedSubjectSet",
      "rule": "(department eq 'Sales')"
    },
    "trigger": {
      "@odata.type": "#microsoft.graph.identityGovernance.timeBasedAttributeTrigger",
      "timeBasedAttribute": "employeeLeaveDateTime",
      "offsetInDays": 0
    }
  },
  "tasks": [
    {
      "category": "leaver",
      "continueOnError": false,
      "displayName": "Revoke all refresh tokens for user",
      "isEnabled": true,
      "taskDefinitionId": "509589a4-0466-4471-829e-49c5e502bdee",
      "arguments": []
    },
    {
      "category": "leaver",
      "continueOnError": true,
      "displayName": "Remove user from all teams",
      "isEnabled": true,
      "taskDefinitionId": "81f7b200-2816-4b3b-8c5d-dc556f07b024",
      "arguments": []
    },
    {
      "category": "leaver",
      "continueOnError": true,
      "displayName": "Remove users from all groups",
      "isEnabled": true,
      "taskDefinitionId": "b3a31406-2a15-4c9a-b25b-a658fa5f07fc",
      "arguments": []
    },
    {
      "category": "leaver",
      "continueOnError": false,
      "displayName": "Disable user account",
      "isEnabled": true,
      "taskDefinitionId": "1dfdfcc7-52fa-4c2e-bf3a-e3919cc12950",
      "arguments": []
    }
  ]
}
# Guest governance add-on needed: no
```
