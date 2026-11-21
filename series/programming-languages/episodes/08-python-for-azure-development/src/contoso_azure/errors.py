"""Turn the Azure errors people actually hit into messages that say what to do."""

from __future__ import annotations

from azure.core.exceptions import ClientAuthenticationError, HttpResponseError, ResourceNotFoundError


def explain(error: Exception) -> str:
    if isinstance(error, ClientAuthenticationError):
        return (
            "Could not get a token. Locally: run 'az login' with the account that has access. "
            "In Azure: enable the managed identity. Details:\n" + str(error)
        )
    if isinstance(error, ResourceNotFoundError):
        return "Container or blob not found. Check the container names and the blob name (names are case-sensitive)."
    if isinstance(error, HttpResponseError) and error.status_code == 403:
        code = getattr(error, "error_code", None)
        if str(code) == "AuthorizationPermissionMismatch" or "AuthorizationPermissionMismatch" in str(error):
            return (
                "403 AuthorizationPermissionMismatch: you are signed in, but your identity has no data-plane role. "
                "Assign 'Storage Blob Data Contributor' on the storage account (Owner or Contributor is not enough), "
                "then wait a few minutes: role assignments can take time to propagate."
            )
        return "403 Forbidden: the identity is not allowed to do this. " + str(error).splitlines()[0]
    return f"{type(error).__name__}: {str(error).splitlines()[0] if str(error) else ''}"
