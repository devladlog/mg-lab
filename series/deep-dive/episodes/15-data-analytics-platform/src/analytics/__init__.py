"""Contoso purchase-request analytics: synthetic source data, bronze files, ML scoring and drift checks.

Everything here is plain Python (pandas, numpy, scikit-learn, duckdb) so it runs on the lab laptop and in the tests.
The cloud parts (Data Factory, Synapse serverless SQL) are described in ../adf, ../sql and ../infra.
"""

DEPARTMENTS = {
    "FIN": "Finance",
    "HR": "Human Resources",
    "IT": "Information Technology",
    "MKT": "Marketing",
    "OPS": "Operations",
}
CATEGORIES = ("Hardware", "Software", "Services", "Travel", "Facilities")
STATUSES = ("Submitted", "Approved", "Rejected")
SLA_DAYS = 5          # a decided request that took more than this many calendar days breached the SLA
__version__ = "1.0.0"
