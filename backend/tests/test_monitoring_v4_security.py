"""Regression tests for the monitoring v4 administrative access boundary.

Run from backend with: pytest tests/test_monitoring_v4_security.py
"""
import os
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.routers.monitoring_v4 import require_monitoring_admin


def test_missing_configuration_fails_closed():
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(HTTPException) as err:
            require_monitoring_admin("Bearer anything")
    assert err.value.status_code == 503


def test_legacy_dev_token_is_not_accepted():
    with patch.dict(os.environ, {"MEDISOFT_MONITORING_ADMIN_TOKEN": "dev-token"}):
        with pytest.raises(HTTPException) as err:
            require_monitoring_admin("Bearer dev-token")
    assert err.value.status_code == 503


def test_missing_or_invalid_bearer_is_rejected():
    token = "a" * 40
    with patch.dict(os.environ, {"MEDISOFT_MONITORING_ADMIN_TOKEN": token}):
        for authorization in (None, "", "Bearer wrong", "Basic " + token):
            with pytest.raises(HTTPException) as err:
                require_monitoring_admin(authorization)
            assert err.value.status_code == 401


def test_valid_independent_token_is_accepted():
    token = "b" * 40
    with patch.dict(os.environ, {"MEDISOFT_MONITORING_ADMIN_TOKEN": token}):
        assert require_monitoring_admin("Bearer " + token) is None
