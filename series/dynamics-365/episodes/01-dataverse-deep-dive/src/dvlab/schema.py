"""Table definitions as code: the Project Request table, its columns, its lookup to Account and its alternate key.

Every function returns the exact JSON body that the Dataverse Web API expects (EntityMetadata,
AttributeMetadata, OneToManyRelationshipMetadata, EntityKeyMetadata). Nothing here calls the network,
so the shapes are unit-tested and can be reviewed in a pull request like any other code.

Shapes follow Microsoft Learn:
- Create and update table definitions using the Web API
- Create and update column definitions using the Web API
- Create and update table relationships using the Web API
"""
from __future__ import annotations

from typing import Any, Dict, List

LCID = 1033  # English
PREFIX = "mgl"
TABLE = f"{PREFIX}_projectrequest"          # logical name (always lowercase)
TABLE_SCHEMA = f"{PREFIX}_ProjectRequest"   # schema name (prefix must match the solution publisher)
ENTITY_SET = f"{PREFIX}_projectrequests"    # what the Web API URLs use
KEY_SCHEMA = f"{PREFIX}_RequestCodeKey"
KEY_COLUMNS = [f"{PREFIX}_requestcode"]

# Local choice values use the publisher's option value prefix (here 72700) + a sequence.
PRIORITY = {"Low": 727000000, "Normal": 727000001, "High": 727000002}

ODATA = "Microsoft.Dynamics.CRM."


def label(text: str) -> Dict[str, Any]:
    """A Label with one LocalizedLabel. Only LocalizedLabels is set: UserLocalizedLabel is read-only."""
    return {
        "@odata.type": ODATA + "Label",
        "LocalizedLabels": [
            {"@odata.type": ODATA + "LocalizedLabel", "Label": text, "LanguageCode": LCID}
        ],
    }


def _required(level: str = "None") -> Dict[str, Any]:
    return {"Value": level, "CanBeChanged": True, "ManagedPropertyLogicalName": "canmodifyrequirementlevelsettings"}


def string_column(schema: str, display: str, max_length: int = 100, *, primary: bool = False,
                  required: str = "None", description: str = "") -> Dict[str, Any]:
    col = {
        "@odata.type": ODATA + "StringAttributeMetadata",
        "AttributeType": "String",
        "AttributeTypeName": {"Value": "StringType"},
        "SchemaName": schema,
        "DisplayName": label(display),
        "RequiredLevel": _required(required),
        "MaxLength": max_length,
        "FormatName": {"Value": "Text"},
    }
    if description:
        col["Description"] = label(description)
    if primary:
        col["IsPrimaryName"] = True
    return col


def money_column(schema: str, display: str, description: str = "") -> Dict[str, Any]:
    # PrecisionSource 2 = use the precision of the record's transaction currency.
    col = {
        "@odata.type": ODATA + "MoneyAttributeMetadata",
        "AttributeType": "Money",
        "AttributeTypeName": {"Value": "MoneyType"},
        "SchemaName": schema,
        "DisplayName": label(display),
        "RequiredLevel": _required(),
        "PrecisionSource": 2,
        "MinValue": 0,
    }
    if description:
        col["Description"] = label(description)
    return col


def date_column(schema: str, display: str) -> Dict[str, Any]:
    """A date with no time: Format DateOnly (display) AND DateTimeBehavior DateOnly (storage).

    Without DateTimeBehavior Dataverse defaults to UserLocal, which stores the user's local midnight in UTC
    (a date picked in Lisbon in summer lands on 23:00 the day before). Learn: avoid Date only format with User
    local behavior. DateOnly behavior can't be changed after creation, so it has to be right the first time.
    """
    return {
        "@odata.type": ODATA + "DateTimeAttributeMetadata",
        "AttributeType": "DateTime",
        "AttributeTypeName": {"Value": "DateTimeType"},
        "SchemaName": schema,
        "DisplayName": label(display),
        "RequiredLevel": _required(),
        "Format": "DateOnly",                          # DateTimeFormat enum: DateOnly | DateAndTime
        "DateTimeBehavior": {"Value": "DateOnly"},     # DateTimeBehavior complex type: UserLocal | DateOnly | TimeZoneIndependent
    }


def choice_column(schema: str, display: str, options: Dict[str, int]) -> Dict[str, Any]:
    return {
        "@odata.type": ODATA + "PicklistAttributeMetadata",
        "AttributeType": "Picklist",
        "AttributeTypeName": {"Value": "PicklistType"},
        "SchemaName": schema,
        "DisplayName": label(display),
        "RequiredLevel": _required(),
        "OptionSet": {
            "@odata.type": ODATA + "OptionSetMetadata",
            "IsGlobal": False,
            "OptionSetType": "Picklist",
            "Options": [{"Value": v, "Label": label(k)} for k, v in options.items()],
        },
    }


def project_request_table() -> Dict[str, Any]:
    """EntityMetadata for POST /EntityDefinitions. The primary name column must be in Attributes."""
    return {
        "@odata.type": ODATA + "EntityMetadata",
        "SchemaName": TABLE_SCHEMA,
        "DisplayName": label("Project Request"),
        "DisplayCollectionName": label("Project Requests"),
        "Description": label("A request for a new internal project, with budget and priority."),
        "OwnershipType": "UserOwned",   # can't be changed later: user/team owned enables security by owner and BU
        "IsActivity": False,
        "HasActivities": False,
        "HasNotes": True,
        "ChangeTrackingEnabled": True,  # lets integrations ask "what changed since my last sync token?"
        "Attributes": [
            string_column(f"{PREFIX}_Name", "Name", 200, primary=True, required="ApplicationRequired",
                          description="Short title of the request."),
        ],
    }


def extra_columns() -> List[Dict[str, Any]]:
    """Columns added after the table exists: POST /EntityDefinitions(LogicalName='...')/Attributes."""
    return [
        string_column(f"{PREFIX}_RequestCode", "Request Code", 20, required="ApplicationRequired",
                      description="Business key from the intake system, e.g. PR-0001. Used as the alternate key."),
        money_column(f"{PREFIX}_Budget", "Budget", "Requested budget in the record's currency."),
        date_column(f"{PREFIX}_DueDate", "Due Date"),
        choice_column(f"{PREFIX}_Priority", "Priority", PRIORITY),
    ]


def account_relationship() -> Dict[str, Any]:
    """OneToManyRelationshipMetadata for POST /RelationshipDefinitions: Account (1) -> Project Request (N).

    The lookup column is created in the same call (deep insert through the Lookup navigation property).
    Delete = RemoveLink: deleting an account clears the lookup instead of deleting requests.
    """
    return {
        "@odata.type": ODATA + "OneToManyRelationshipMetadata",
        "SchemaName": f"{PREFIX}_account_projectrequest",
        "ReferencedEntity": "account",
        "ReferencedAttribute": "accountid",
        "ReferencingEntity": TABLE,
        "CascadeConfiguration": {
            "Assign": "NoCascade", "Delete": "RemoveLink", "Merge": "NoCascade",
            "Reparent": "NoCascade", "Share": "NoCascade", "Unshare": "NoCascade",
        },
        "Lookup": {
            "@odata.type": ODATA + "LookupAttributeMetadata",
            "AttributeType": "Lookup",
            "AttributeTypeName": {"Value": "LookupType"},
            "SchemaName": f"{PREFIX}_CustomerAccountId",
            "DisplayName": label("Customer Account"),
            "RequiredLevel": _required(),
        },
    }


def request_code_key() -> Dict[str, Any]:
    """EntityKeyMetadata for POST /EntityDefinitions(LogicalName='...')/Keys.

    The key's index is built by a background job: EntityKeyIndexStatus goes Pending -> InProgress -> Active
    (or Failed). Upserts by this key only work once it is Active.
    """
    return {
        "SchemaName": KEY_SCHEMA,
        "DisplayName": label("Request Code"),
        "KeyAttributes": KEY_COLUMNS,
    }
