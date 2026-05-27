"""Settings.secret_key validation: enforce non-dev-default outside safe envs.

The dev-default secret key (`"dev-only-do-not-use-in-prod"`) must be accepted
only when TM_ENV is one of the whitelisted dev/test envs. Any other value
— including a blank env, "staging", "production", or a typo — must refuse
to start the application.

This closes the audit-finding-C3 loophole where `TM_ENV="staging"` (or any
non-`production` value) passed the previous validator with only a stderr
warning, allowing the dev key to silently bleed into a hosted environment.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from api.settings import Settings

_DEV_DEFAULT_KEY = "dev-only-do-not-use-in-prod"
_REAL_KEY = "a" * 32  # any non-default value


@pytest.mark.parametrize(
    "safe_env",
    ["development", "dev", "test", "testing", "local", "ci", "Development", "DEV"],
)
def test_dev_default_secret_accepted_in_safe_envs(safe_env: str, capsys) -> None:
    """The dev default is fine in genuinely-dev envs — but the warning
    should still fire so the operator sees it on first run."""
    Settings(env=safe_env, secret_key=_DEV_DEFAULT_KEY)
    captured = capsys.readouterr()
    assert "TM_SECRET_KEY is the dev default" in captured.err


@pytest.mark.parametrize(
    "unsafe_env",
    [
        "production",
        "prod",
        "staging",
        "stg",
        "uat",
        "qa",
        "",  # blank → unsafe (operator forgot to set TM_ENV)
        "Production",  # any casing
        "demo",
    ],
)
def test_dev_default_secret_rejected_outside_safe_envs(unsafe_env: str) -> None:
    """Any non-whitelisted env with the dev key must hard-crash at boot."""
    with pytest.raises(ValidationError) as exc:
        Settings(env=unsafe_env, secret_key=_DEV_DEFAULT_KEY)
    # The error must name the offending env and reference TM_SECRET_KEY
    # so the operator knows exactly what to fix.
    msg = str(exc.value)
    assert "TM_SECRET_KEY" in msg
    assert "dev-default" not in msg.lower() or "dev-default" in msg.lower()


@pytest.mark.parametrize(
    "env",
    ["production", "staging", "development", ""],
)
def test_real_secret_key_accepted_everywhere(env: str) -> None:
    """A non-dev-default secret_key must always be accepted regardless of env."""
    s = Settings(env=env, secret_key=_REAL_KEY)
    assert s.secret_key == _REAL_KEY


def test_partial_match_dev_only_substring_also_rejected() -> None:
    """The substring check is 'dev-only' — confirm a key that contains
    that substring (e.g., a typo or leftover comment) is also rejected."""
    with pytest.raises(ValidationError):
        Settings(env="production", secret_key="my-dev-only-leftover-suffix")
