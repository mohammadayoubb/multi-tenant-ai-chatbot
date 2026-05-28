"""Tests for service-to-service authentication helpers.

Owner: Ayoub / Owner C
"""

from app.infra.service_auth import validate_bearer_token


def test_service_auth_rejects_missing_expected_token() -> None:
    """Validation should fail if the service token is not configured."""

    result = validate_bearer_token(
        authorization="Bearer test-token",
        expected_token=None,
    )

    assert result.is_valid is False
    assert result.reason == "Service token is not configured."


def test_service_auth_rejects_missing_authorization_header() -> None:
    """Validation should fail if Authorization header is missing."""

    result = validate_bearer_token(
        authorization=None,
        expected_token="test-token",
    )

    assert result.is_valid is False
    assert result.reason == "Missing Authorization header."


def test_service_auth_rejects_wrong_token() -> None:
    """Validation should fail when the token is wrong."""

    result = validate_bearer_token(
        authorization="Bearer wrong-token",
        expected_token="test-token",
    )

    assert result.is_valid is False
    assert result.reason == "Invalid service credentials."


def test_service_auth_accepts_correct_token() -> None:
    """Validation should pass when the Bearer token matches."""

    result = validate_bearer_token(
        authorization="Bearer test-token",
        expected_token="test-token",
    )

    assert result.is_valid is True
    assert result.reason == "Service credentials are valid."