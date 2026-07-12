"""Smoke tests: the package and its declarative schema import and are well-formed."""

from __future__ import annotations


def test_package_imports():
    import cta2045_proxy  # noqa: F401
    from cta2045_proxy import cli, core, emitter, mapping  # noqa: F401
    from cta2045_proxy.ucm import build_backend  # noqa: F401


def test_specs_are_well_formed():
    from cta2045_proxy import mapping
    from ebus_sdk import PropertySpec

    for spec in [*mapping.BRIDGE_SPECS, *mapping.water_heater_specs(lambda v: None)]:
        assert isinstance(spec, PropertySpec)
        assert spec.capability and spec.prop_id

    specs = mapping.water_heater_specs(lambda v: None)

    # flex/request is settable, carries its entity_setter (auto-wired at build),
    # and advertises its control surface via a json $format JSONSchema.
    request = next(s for s in specs if s.capability == "flex" and s.prop_id == "request")
    assert request.settable and request.entity_setter is not None
    assert request.format, "flex/request must advertise a $format JSONSchema"

    # response and opt-out are enums with their allowed-value lists.
    response = next(s for s in specs if s.capability == "flex" and s.prop_id == "response")
    assert "NONE" in response.format and "CURTAILED" in response.format
    opt_out = next(s for s in specs if s.capability == "flex" and s.prop_id == "opt-out")
    assert opt_out.format == "NONE,LOCAL,GRID,ALL"

    # Reported properties whose CTA-2045 source is a determinate value set are
    # enums carrying that set (not bare strings), matching the eBus catalogs.
    from ebus_sdk import PropertyDatatype

    all_specs = [*mapping.BRIDGE_SPECS, *specs]
    enum_formats = {
        ("status", "fault-state"): "OK,FAULT,UNKNOWN",
        ("connection", "feeds-device-status"): "OK,LOST,DEGRADED",
        ("info", "fuel-type"): "ELECTRIC,GAS,HEAT_PUMP,HYBRID,OTHER",
    }
    for (cap, pid), fmt in enum_formats.items():
        spec = next(s for s in all_specs if s.capability == cap and s.prop_id == pid)
        assert spec.datatype == PropertyDatatype.ENUM, f"{cap}/{pid} should be an enum"
        assert spec.format == fmt


def test_unknown_backend_kind_raises():
    import pytest

    from cta2045_proxy.ucm import build_backend

    with pytest.raises(ValueError):
        build_backend({"ucm": {"kind": "nope"}}, {}, lambda *a: None, lambda *a: None, lambda *a: None)
