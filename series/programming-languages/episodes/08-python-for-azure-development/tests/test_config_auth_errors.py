from __future__ import annotations

import pytest
from azure.core.exceptions import ClientAuthenticationError, HttpResponseError, ResourceNotFoundError
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential

from contoso_azure.auth import build_credential
from contoso_azure.config import ConfigError, Settings
from contoso_azure.errors import explain


def test_settings_from_env_need_the_account_url() -> None:
    with pytest.raises(ConfigError, match="CONTOSO_STORAGE_ACCOUNT_URL"):
        Settings.from_env({})


def test_settings_defaults_and_trailing_slash() -> None:
    settings = Settings.from_env({"CONTOSO_STORAGE_ACCOUNT_URL": "https://stcontoso.blob.core.windows.net/"})
    assert settings == Settings("https://stcontoso.blob.core.windows.net", "requests", "packs")


@pytest.mark.parametrize("name", ["ab", "Requests", "my_container", "-abc", "abc-", "a--b", "x" * 64])
def test_invalid_container_names_fail_before_any_network_call(name: str) -> None:
    with pytest.raises(ConfigError, match="not a valid container name"):
        Settings.create("https://stcontoso.blob.core.windows.net", name, "packs")


@pytest.mark.parametrize("name", ["abc", "requests", "packs-2026", "x" * 63])
def test_valid_container_names(name: str) -> None:
    assert Settings.create("https://stcontoso.blob.core.windows.net", name, "packs").input_container == name


def test_a_url_that_is_not_an_endpoint_is_rejected() -> None:
    with pytest.raises(ConfigError, match="not a blob endpoint URL"):
        Settings.create("stcontoso", "requests", "packs")


def test_dev_mode_is_the_default_chain_without_the_managed_identity_attempt() -> None:
    assert isinstance(build_credential("dev"), DefaultAzureCredential)


def test_azure_mode_is_exactly_the_managed_identity() -> None:
    credential = build_credential("azure", managed_identity_client_id="00000000-0000-0000-0000-000000000000")
    assert type(credential) is ManagedIdentityCredential


def test_unknown_mode_is_an_error() -> None:
    with pytest.raises(ValueError, match="Unknown auth mode"):
        build_credential("prod")


def _http_error(status: int, error_code: str) -> HttpResponseError:
    error = HttpResponseError(message=f"{status} {error_code}")
    error.status_code = status
    error.error_code = error_code  # type: ignore[attr-defined]
    return error


def test_403_without_a_data_plane_role_says_which_role_to_assign() -> None:
    text = explain(_http_error(403, "AuthorizationPermissionMismatch"))
    assert "Storage Blob Data Contributor" in text
    assert "Owner or Contributor is not enough" in text


def test_other_errors_get_short_messages() -> None:
    assert "az login" in explain(ClientAuthenticationError("no credential"))
    assert "not found" in explain(ResourceNotFoundError("gone"))
    assert explain(_http_error(403, "Other")).startswith("403 Forbidden")
    assert explain(_http_error(500, "InternalError")).startswith("HttpResponseError")
