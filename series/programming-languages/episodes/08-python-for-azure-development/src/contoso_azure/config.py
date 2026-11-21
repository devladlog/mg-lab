"""Settings from the environment, validated before the first network call."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from urllib.parse import urlparse

# Learn: 3-63 characters, lowercase letters, numbers and hyphens, start and end with a letter or number,
# no consecutive hyphens.
_CONTAINER = re.compile(r"(?!.*--)[a-z0-9][a-z0-9-]{1,61}[a-z0-9]")


class ConfigError(ValueError):
    """The settings are wrong; the message says which one and how to fix it."""


@dataclass(frozen=True, slots=True)
class Settings:
    account_url: str
    input_container: str = "requests"
    output_container: str = "packs"

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Settings:
        source = os.environ if env is None else env
        account_url = source.get("CONTOSO_STORAGE_ACCOUNT_URL", "")
        if not account_url:
            raise ConfigError("Set CONTOSO_STORAGE_ACCOUNT_URL, for example https://<account>.blob.core.windows.net")
        return cls.create(
            account_url,
            source.get("CONTOSO_INPUT_CONTAINER", "requests"),
            source.get("CONTOSO_OUTPUT_CONTAINER", "packs"),
        )

    @classmethod
    def create(cls, account_url: str, input_container: str, output_container: str) -> Settings:
        parsed = urlparse(account_url)
        if parsed.scheme not in ("https", "http") or not parsed.netloc:
            raise ConfigError(f"'{account_url}' is not a blob endpoint URL (https://<account>.blob.core.windows.net).")
        for name in (input_container, output_container):
            if not _CONTAINER.fullmatch(name):
                raise ConfigError(
                    f"'{name}' is not a valid container name: 3-63 lowercase letters, numbers and single hyphens."
                )
        return cls(account_url.rstrip("/"), input_container, output_container)
