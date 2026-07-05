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

    # dr/event is settable and carries its entity_setter (auto-wired at build).
    event = next(s for s in mapping.water_heater_specs(lambda v: None) if s.prop_id == "event")
    assert event.settable and event.entity_setter is not None


def test_unknown_backend_kind_raises():
    import pytest

    from cta2045_proxy.ucm import build_backend

    with pytest.raises(ValueError):
        build_backend({"ucm": {"kind": "nope"}}, {}, lambda *a: None, lambda *a: None, lambda *a: None)
