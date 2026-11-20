# Dataverse data model — MG Lab Demo solution

Publisher **MG Lab** (prefix `mgl`, option value prefix `10500`) · Solution **MGLabDemo** (unmanaged in DEV).

## mgl_department (organization-owned)
| Column | Schema name | Type |
|---|---|---|
| Name (primary) | `mgl_Name` | Text (100), required |

## mgl_projectrequest (user/team-owned, auditing on, notes on)
| Column | Schema name | Type | Notes |
|---|---|---|---|
| Title (primary) | `mgl_Title` | Text (200) | required |
| Requester | `mgl_Requester` | Text (100) | |
| Department | `mgl_DepartmentId` | Lookup → mgl_department | relationship `mgl_department_projectrequest`, delete = remove link |
| Budget | `mgl_Budget` | Currency | |
| Request Status | `mgl_RequestStatus` | Choice | New, In review, Approved, Rejected, Done (105000000–105000004) |
| Priority | `mgl_Priority` | Choice | Low, Medium, High (105000000–105000002) |
| Due Date | `mgl_DueDate` | Date only | |

Security: assign a custom role with **User**-level read/write on Project Request for requesters,
**Business unit** level for managers, **Organization** level for the PMO.

The script [`create-model.js`](create-model.js) creates all of this through the Dataverse Web API.
