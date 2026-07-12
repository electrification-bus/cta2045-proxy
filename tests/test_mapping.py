"""flex/request encode path: $format validation + CTA-2045 translation."""

from __future__ import annotations

from cta2045_proxy import mapping


def test_valid_shed_request_translates():
    # A well-formed request within the advertised control surface produces a
    # CTA-2045 message (duration is an allowed additional property).
    msg = mapping.command_for_flex_request({"mode": "SHED", "duration": 600})
    assert msg is not None


def test_normal_request_translates_to_end():
    assert mapping.command_for_flex_request({"mode": "NORMAL"}) is not None


def test_request_accepts_json_string_payload():
    # An inbound /set may arrive as a JSON string, not a parsed dict.
    assert mapping.command_for_flex_request('{"mode":"SHED"}') is not None


def test_invalid_mode_is_rejected_by_format():
    # BOGUS is not in the $format's mode enum, so validation rejects it before
    # any CTA-2045 translation.
    assert mapping.command_for_flex_request({"mode": "BOGUS"}) is None


def test_missing_required_mode_is_rejected():
    assert mapping.command_for_flex_request({"intensity": "PEAK"}) is None
