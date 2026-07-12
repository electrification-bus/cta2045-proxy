"""flex/request encode path: $format validation + CTA-2045 translation."""

from __future__ import annotations

from cta2045 import app

from cta2045_proxy import mapping


def test_valid_shed_request_translates():
    # A well-formed request within the advertised control surface produces a
    # CTA-2045 message (duration is an allowed field).
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


def test_cause_is_accepted():
    # cause is advisory but part of the accepted surface.
    assert mapping.command_for_flex_request({"mode": "SHED", "cause": "GRID_OPTIMIZATION"}) is not None


def test_unsupported_fields_are_rejected():
    # The schema is strict (additionalProperties: false): fields this device does
    # not support are rejected rather than silently ignored.
    assert mapping.command_for_flex_request({"mode": "LOAD_UP", "temporary-setpoint": 60.0}) is None
    assert mapping.command_for_flex_request({"mode": "SHED", "level": 50}) is None


def test_target_percentage_encodes_advanced_load_up():
    # LOAD_UP + ADVANCED + target-percentage, with known storage, becomes an
    # Advanced Load Up carrying the extra Wh: (80% of 4500) - 1000 = 2600 Wh.
    msg = mapping.command_for_flex_request(
        {"mode": "LOAD_UP", "intensity": "ADVANCED", "target-percentage": 80, "duration": 3600},
        capacity_wh=4500.0,
        current_wh=1000.0,
    )
    assert isinstance(msg, app.AdvancedLoadUp)
    assert msg.value * (10**msg.units.value) == 2600
    assert msg.duration_minutes == 60


def test_advanced_load_up_falls_back_without_storage():
    # Same request, but the device has not reported its storage: fall back to
    # Basic DR load-up rather than guessing an energy target.
    msg = mapping.command_for_flex_request(
        {"mode": "LOAD_UP", "intensity": "ADVANCED", "target-percentage": 80},
    )
    assert isinstance(msg, app.BasicDR)


def test_quantize_load_up_wh_fits_16_bit():
    # A value too large for the finest unit steps up to a coarser Wh unit.
    value, units = mapping._quantize_load_up_wh(200_000)
    assert value <= 0xFFFF
    assert value * (10**units.value) == 200_000
