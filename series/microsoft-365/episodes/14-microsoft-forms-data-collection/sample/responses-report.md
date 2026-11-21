# Forms responses: Microsoft 365 Apps rollout pulse

_As of 2026-11-25 12:00:00Z._

**9 response(s).**

| Question | Answered | Result |
|---|---|---|
| Department | 8 | Finance: 1, Sales: 2, IT: 3, Operations: 1 |
| Rating | 9 | average 4 (min 1, max 7); 1: 1, 2: 1, 3: 1, 4: 2, 5: 3 |
| AppIssue | 9 | Word: 1, Excel: 1, Outlook: 2, PowerPoint: 1, Teams: 2, None: 3 |
| Comment | 7 |  |
| ContactMe | 9 | yes 2, no 7 |
| IncidentDate | 4 |  |

Per day (UTC): 2026-11-23: 4, 2026-11-24: 5

**9 data-quality finding(s):** 1 High / 3 Medium / 3 Low / 2 Info

| Severity | Type | Response | Detail |
|---|---|---|---|
| High | DuplicateResponseId | 3 | 2 rows for one Forms response (a flow retry or a second flow). |
| Medium | InvalidChoice | 5 | 'Department' holds 'Legal', which is not one of the choices. |
| Medium | MissingRequired | 4 | 'Department' is required in the spec and empty. |
| Medium | OutOfRange | 5 | 'Rating' is 7, outside 1..5. |
| Low | LowRatingNoComment | 2 | Rating 2 with no 'Comment': nothing to act on. |
| Low | LowRatingNoComment | 6 | Rating 1 with no 'Comment': nothing to act on. |
| Low | PossibleDoubleSubmit | 9 | Same answers as response 8 from the same responder 3 min earlier. |
| Info | AnonymousResponder | 6 | No responder recorded: an anonymous response, or the form or tenant does not record names. |
| Info | ResponseIdGap | 7 | No row for response id(s) 7: deleted in Forms, or the flow missed them. Compare with the Forms Responses tab. |

