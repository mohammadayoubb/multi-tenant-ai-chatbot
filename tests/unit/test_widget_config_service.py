# Owner: Amer
"""Unit tests for widget configuration service helpers (feature 004).

The HTTP-layer + diff + audit behavior is covered in
tests/security/test_widget_admin_config.py against the FastAPI app. This file
covers the pure helpers in isolation so a regression in normalization shows up
without spinning up the app.
"""

from __future__ import annotations

import pytest

from app.services.widget_service import normalize_origin


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("https://customer-site.example", "https://customer-site.example"),
        ("https://CUSTOMER-site.example", "https://customer-site.example"),
        ("HTTPS://customer-site.example", "https://customer-site.example"),
        ("https://customer-site.example/", "https://customer-site.example"),
        ("https://customer-site.example/some/path", "https://customer-site.example"),
        ("https://customer-site.example?q=1", "https://customer-site.example"),
        ("https://customer-site.example#frag", "https://customer-site.example"),
        ("https://customer-site.example:443", "https://customer-site.example"),
        ("http://customer-site.example:80", "http://customer-site.example"),
        ("http://customer-site.example:5500", "http://customer-site.example:5500"),
        ("https://customer-site.example:8443", "https://customer-site.example:8443"),
    ],
)
def test_normalize_origin_canonical_forms(raw, expected):
    assert normalize_origin(raw) == expected


@pytest.mark.parametrize(
    "bad",
    [
        "ftp://customer-site.example",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "data:text/html,foo",
        "customer-site.example",  # no scheme
        "https://",  # no host
        "https:///",  # no host
        "",  # empty
        "not a url at all",
    ],
)
def test_normalize_origin_raises_on_invalid(bad):
    with pytest.raises(ValueError):
        normalize_origin(bad)
