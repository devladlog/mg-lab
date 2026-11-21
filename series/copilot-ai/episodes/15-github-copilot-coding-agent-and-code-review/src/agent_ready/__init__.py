"""agent_ready: preflight checks for GitHub Copilot cloud agent (formerly coding agent) and Copilot code review."""

from .findings import Finding, has_errors

__all__ = ["Finding", "has_errors"]
