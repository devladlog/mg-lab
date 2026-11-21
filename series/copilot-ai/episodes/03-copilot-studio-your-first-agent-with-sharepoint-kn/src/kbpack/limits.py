"""Limits for SharePoint knowledge sources, each with the Microsoft Learn page that states it.

Verified 21 Nov 2026 against:
  SITE  https://learn.microsoft.com/microsoft-copilot-studio/requirements-quotas  (section "SharePoint web app limits")
  FILES https://learn.microsoft.com/microsoft-copilot-studio/knowledge-add-unstructured-data  (Upload files > SharePoint)
  TROUBLE https://learn.microsoft.com/troubleshoot/power-platform/copilot-studio/knowledge/sharepoint-no-response
"""
from __future__ import annotations

MB = 1024 * 1024

SITE_URL = "https://learn.microsoft.com/microsoft-copilot-studio/requirements-quotas#sharepoint-web-app-limits"
FILES_URL = "https://learn.microsoft.com/microsoft-copilot-studio/requirements-quotas#limits"
TROUBLE_URL = ("https://learn.microsoft.com/troubleshoot/power-platform/copilot-studio/knowledge/"
               "sharepoint-no-response")

# "SharePoint" option (site / folder URL, full SharePoint integration)
SITE_TYPES = {".doc", ".docx", ".ppt", ".pptx", ".pdf"}
# Excel is not in the site list, but Learn says XLSX can be added with weak answers to analytical questions.
SITE_WEAK_TYPES = {".xls", ".xlsx"}
SITE_MAX_BYTES_NO_M365 = 7 * MB       # no Microsoft 365 Copilot licence in the agent's tenant
SITE_MAX_BYTES_M365 = 200 * MB        # licence + "Tenant graph grounding with semantic search" on
MAX_SITE_URLS_PER_AGENT = 25          # with generative orchestration

# "Upload files > SharePoint" option (files and folders, synchronised into Dataverse)
FILES_TYPES = {".doc", ".docx", ".ppt", ".pptx", ".pdf", ".xls", ".xlsx"}
FILES_MAX_BYTES = 512 * MB
FILES_MAX_FILES = 1000
FILES_MAX_FOLDERS = 50
FILES_MAX_DEPTH = 10

OOXML = {".docx", ".pptx", ".xlsx"}
OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"   # OLE compound file: how a password-protected OOXML file starts
