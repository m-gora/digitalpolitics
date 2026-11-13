"""Unit tests for the display-name resolution chain in dpp.auth.headers.

The chain: first non-empty of the name-ish header, then the email header,
else None. X-User-Id remains the identity key regardless (arch-01/adr-03).
"""

import pytest
from starlette.requests import Request

from dpp.auth.headers import parse_identity


def _request(headers: dict[str, str]) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
    }
    return Request(scope)


def test_display_name_from_the_name_header():
    identity = parse_identity(
        _request(
            {
                "X-User-Id": "sub-123",
                "X-Auth-Request-Preferred-Username": "Anna Berg",
                "X-Auth-Request-Email": "anna@example.org",
            }
        )
    )
    assert identity is not None
    assert identity.user_id == "sub-123"
    assert identity.display_name == "Anna Berg"


def test_display_name_falls_back_to_email_header():
    identity = parse_identity(
        _request({"X-User-Id": "sub-123", "X-Auth-Request-Email": "anna@example.org"})
    )
    assert identity is not None
    assert identity.display_name == "anna@example.org"


def test_display_name_none_when_neither_header_present():
    identity = parse_identity(_request({"X-User-Id": "sub-123"}))
    assert identity is not None
    assert identity.display_name is None


def test_empty_name_header_falls_through_to_email():
    identity = parse_identity(
        _request(
            {
                "X-User-Id": "sub-123",
                "X-Auth-Request-Preferred-Username": "",
                "X-Auth-Request-Email": "anna@example.org",
            }
        )
    )
    assert identity is not None
    assert identity.display_name == "anna@example.org"


def test_no_identity_without_user_id():
    assert parse_identity(_request({"X-Auth-Request-Preferred-Username": "Anna Berg"})) is None


def test_groups_claim_expands_to_district_scopes():
    # "lv-berlin" inherits bv-mitte and ov-wedding per the arch-02 rule
    # (as configured in config/gliederungen.yaml); "all" sees everything,
    # including the bundesverband root.
    identity = parse_identity(
        _request({"X-User-Id": "sub-123", "X-Auth-Request-Groups": "lv-berlin"})
    )
    assert identity is not None
    assert identity.district_scopes == frozenset(
        {"lv-berlin", "bv-friedrichshain-kreuzberg", "bv-mitte", "ov-kreuzberg", "ov-friedrichshain", "ov-wedding"}
    )
    assert identity.has_write_access("ov-wedding")
    assert not identity.has_write_access("bundesverband")

    all_identity = parse_identity(_request({"X-User-Id": "sub-123", "X-Auth-Request-Groups": "all"}))
    assert all_identity is not None
    assert all_identity.district_scopes == frozenset(
        {"bundesverband", "lv-berlin", "bv-friedrichshain-kreuzberg", "bv-mitte", "ov-kreuzberg", "ov-friedrichshain", "ov-wedding"}
    )

    unknown_identity = parse_identity(
        _request({"X-User-Id": "sub-123", "X-Auth-Request-Groups": "some-random-group"})
    )
    assert unknown_identity is not None
    assert unknown_identity.district_scopes == frozenset()
