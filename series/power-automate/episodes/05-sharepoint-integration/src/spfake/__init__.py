"""spfake: an in-memory SharePoint site (lists, versions, change log, library folders, permissions and the
REST endpoints our flow uses) for testing SharePoint cloud flows locally. Test double, not SharePoint."""
from .scenario import PARAMS, SITE_URL, Poller, first_version, purchasing_site, user
from .site import Site, SPError, SPList, token

__all__ = ["PARAMS", "SITE_URL", "Poller", "first_version", "purchasing_site", "user", "Site", "SPError", "SPList", "token"]
