"""CTA-2045 semantics <-> eBus water-heater data model.

Pure translation: no MQTT, no Homie devices. This module owns

- the declarative `PropertySpec` tables for the bridge (UCM) root device and
  the proxied water-heater child (the single source of truth that
  `ebus_sdk.build_from_declarations` materializes into both the observable
  model and the Homie tree), and
- the decode-direction handlers that turn a decoded `cta2045.app` message into
  observable-model updates, plus the encode-direction translation of a Homie
  `dr/event` command back into a CTA-2045 application message.

Data-model reference: ../../specification/data-models/water-heater.md
(§Example: CTA-2045 water heater). Built against ebus-sdk 0.8's declarative
proxy layer (PropertySpec + build_from_declarations).
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from cta2045 import app
from cta2045.enums import CommodityCode, OperationalState

from ebus_sdk import PropertyDatatype, PropertySpec, Unit

# GroupedPropertyDict is the homie-agnostic observable model; depending on it
# here (not on homie.Device) keeps this module transport-free.
from ebus_sdk import GroupedPropertyDict


# --- Declarative schema: the UCM bridge root ---------------------------------
# capability (Homie node id) -> its properties. build_from_declarations groups
# by capability and defaults each node type to energy.ebus.capability.<cap>.
BRIDGE_SPECS: list[PropertySpec] = [
    PropertySpec("info", "vendor-name", PropertyDatatype.STRING),
    PropertySpec("info", "firmware-version", PropertyDatatype.STRING),
    PropertySpec("connection", "feeds-device-id", PropertyDatatype.STRING),
    PropertySpec("connection", "feeds-device-type", PropertyDatatype.STRING),
    PropertySpec("connection", "feeds-device-status", PropertyDatatype.STRING),
    # last-seen: the UCM's own report timestamp (from the SkyCentrics /data "t"
    # field), as an ISO-8601 UTC datetime. Not part of the eBus data model; a
    # liveness/freshness heartbeat, updated on every message the UCM sends.
    PropertySpec("connection", "last-seen", PropertyDatatype.DATETIME),
]


# --- Declarative schema: the proxied water-heater child ----------------------
# A factory rather than a module constant: the settable `dr/event` property's
# entity_setter is a per-device bound method (it needs the device's UCM + model),
# so it must be supplied at build time. build_from_declarations (ebus-sdk >=0.9)
# wires the whole inbound /set path from settable=True + entity_setter.
def water_heater_specs(on_dr_event_set: Callable) -> list[PropertySpec]:
    """PropertySpecs for the water-heater child, with dr/event bound to its setter."""
    return [
        PropertySpec("info", "fuel-type", PropertyDatatype.STRING),
        PropertySpec("meter", "active-power", PropertyDatatype.FLOAT, Unit.WATT),
        PropertySpec("meter", "imported-energy", PropertyDatatype.FLOAT, Unit.WATT_HOUR),
        PropertySpec("soc", "soe", PropertyDatatype.FLOAT, Unit.WATT_HOUR),
        PropertySpec("soc", "total-energy-storage", PropertyDatatype.FLOAT, Unit.WATT_HOUR),
        PropertySpec("soc", "loadup-headroom", PropertyDatatype.FLOAT, Unit.WATT_HOUR),
        PropertySpec("dr", "dr-response", PropertyDatatype.STRING),
        PropertySpec("dr", "opted-out", PropertyDatatype.BOOLEAN),
        # Settable (controller -> device): an arriving /set routes through the
        # model to on_dr_event_set, which translates it to a CTA-2045 command.
        PropertySpec("dr", "event", PropertyDatatype.JSON, settable=True, entity_setter=on_dr_event_set),
        PropertySpec("dr", "active-event", PropertyDatatype.JSON),
        PropertySpec("status", "fault-state", PropertyDatatype.STRING),
    ]


# Decomposition of CTA-2045 OperationalState onto the data-model surface
# (data-models/water-heater.md §Example). Value: (dr_response, opted_out, fault).
OP_STATE_DECOMPOSITION: dict[OperationalState, tuple] = {
    OperationalState.Idle_Normal: ("NONE", False, False),
    OperationalState.Running_Normal: ("NONE", False, False),
    OperationalState.Idle_Curtailed: ("CURTAILED", False, False),
    OperationalState.Running_Curtailed: ("CURTAILED", False, False),
    OperationalState.Idle_Heightened: ("BOOSTED", False, False),
    OperationalState.Running_Heightened: ("BOOSTED", False, False),
    OperationalState.Idle_Opted_Out: ("NONE", True, False),
    OperationalState.Running_Opted_Out: ("NONE", True, False),
    # Variable Following: spec says BOOSTED-or-CURTAILED depending on the last
    # event; without that history we map conservatively.
    OperationalState.Variable_Following: ("NOT_FOLLOWING", False, False),
    OperationalState.Variable_Not_Following: ("NOT_FOLLOWING", False, False),
    OperationalState.SGD_Error: ("NONE", False, True),
    OperationalState.Cycling_On: ("NONE", False, False),
    OperationalState.Cycling_Off: ("NONE", False, False),
    OperationalState.Running_Price_Stream: ("NONE", False, False),
    OperationalState.Idle_Price_Stream: ("NONE", False, False),
}


# --- Decode direction: CTA-2045 message -> observable-model updates ----------


def apply_decoded(
    message,
    bridge: GroupedPropertyDict,
    wh: GroupedPropertyDict,
    log: Optional[logging.Logger] = None,
) -> None:
    """Route one decoded CTA-2045 message into the two observable models.

    `bridge` holds the UCM device's live values; `wh` the water-heater child's.
    Updates flow to Homie automatically via the on-change bindings the emitter
    registered. BasicDR carries operational state in query responses; the rich
    replies arrive wrapped in IntermediateDR.
    """
    log = log or logging.getLogger("cta2045_proxy.mapping")

    # Local import keeps the module top-level lean and tolerant of app-layer
    # symbol churn across cta2045 releases.
    from cta2045.app import (
        AdvancedLoadUp,
        BasicDR,
        CommodityReadReply,
        GetInformationReply,
        IntermediateDR,
    )

    if isinstance(message, BasicDR):
        op_state = getattr(message, "operational_state", None)
        if op_state is not None:
            _apply_operational_state(op_state, wh)
        return

    if isinstance(message, IntermediateDR):
        body = getattr(message, "body", None)
        if isinstance(body, CommodityReadReply):
            _apply_commodity_read_reply(body, wh)
        elif isinstance(body, GetInformationReply):
            _apply_get_information_reply(body, wh)
        elif isinstance(body, AdvancedLoadUp):
            # TODO(repo-local): AdvancedLoadUp reply carries present/forecast
            # energy-storage quantities that map to soc/loadup-headroom. Decode
            # and update once the lib field names are confirmed against captured
            # frames.
            log.debug("reason=advancedLoadUpPending")
        return

    log.debug(f"reason=dispatchUnhandled,type={type(message).__name__}")


def _apply_operational_state(state: OperationalState, wh: GroupedPropertyDict) -> None:
    dr_response, opted_out, fault = OP_STATE_DECOMPOSITION.get(state, ("NONE", False, False))
    wh.set_value("dr", "dr-response", dr_response)
    wh.set_value("dr", "opted-out", opted_out)
    wh.set_value("status", "fault-state", "FAULT" if fault else "OK")


def _apply_commodity_read_reply(reply, wh: GroupedPropertyDict) -> None:
    for report in getattr(reply, "reports", []):
        code = getattr(report, "code", None)
        if code == CommodityCode.Electricity_Consumed:
            wh.set_value("meter", "active-power", float(report.instantaneous))
            wh.set_value("meter", "imported-energy", float(report.cumulative))
        elif code == CommodityCode.Total_Energy_Storage:
            wh.set_value("soc", "total-energy-storage", float(report.cumulative))
            wh.set_value("soc", "soe", float(report.instantaneous))


def _apply_get_information_reply(reply, wh: GroupedPropertyDict) -> None:
    # GetInformationReply describes the SGD (the appliance), so its firmware and
    # device-type belong to the water-heater child, NOT the bridge. The bridge
    # (UCM) firmware/vendor come from the backend's own metadata (e.g. the
    # SkyCentrics devinfo JSON) via set_bridge_info, independent of any SGD.
    #
    # TODO(repo-local): the water-heater `info` capability has no firmware-version
    #   property yet; add one to WATER_HEATER_SPECS to surface firmware_version(reply).
    # TODO(repo-local): device-type -> wh info/fuel-type (Water_Heater_Gas -> GAS,
    #   Water_Heater_HeatPump -> HEAT_PUMP, ...).
    _ = firmware_version(reply)  # noqa: F841 - retained until wh firmware property exists


def firmware_version(reply) -> Optional[str]:
    """Compose GetInformationReply fw_* fields into one version string.

    GetInformationReply exposes fw_year/fw_month/fw_day/fw_major/fw_minor as
    separate optional fields (CTA-2045-B § 11.1.1.2).
    """
    major = getattr(reply, "fw_major", None)
    minor = getattr(reply, "fw_minor", None)
    if major is None and minor is None:
        return None
    version = f"{major or 0}.{minor or 0}"
    y = getattr(reply, "fw_year", None)
    m = getattr(reply, "fw_month", None)
    d = getattr(reply, "fw_day", None)
    if y is not None and m is not None and d is not None:
        return f"{version} ({y:04d}-{m:02d}-{d:02d})"
    return version


# --- Encode direction: Homie dr/event command -> CTA-2045 message ------------


def command_for_dr_event(event_value, log: Optional[logging.Logger] = None):
    """Translate a `dr/event` JSON object into a CTA-2045 application message.

    Returns a `cta2045.app` message ready for `Ucm.send`, or None if the event
    could not be translated (unknown mode / parse failure). The caller owns the
    transport; this function is pure.
    """
    import json

    log = log or logging.getLogger("cta2045_proxy.mapping")
    try:
        evt = json.loads(event_value) if isinstance(event_value, (str, bytes)) else event_value
        mode = evt.get("mode", "NORMAL")
        intensity = evt.get("intensity")
        duration_s = evt.get("duration")
        duration_min = (duration_s / 60.0) if duration_s is not None else None

        if mode == "NORMAL":
            return app.end()
        if mode == "SHED":
            if intensity == "EMERGENCY":
                return app.grid_emergency(duration_min)
            if intensity == "PEAK":
                return app.critical_peak(duration_min)
            return app.shed(duration_min)
        if mode == "LOAD_UP":
            # TODO(repo-local): intensity=ADVANCED -> advanced_load_up(...) needs
            # value + units (Wh quantization) supplied in the event JSON.
            return app.load_up(duration_min)

        log.warning(f"reason=drEventUnknownMode,mode={mode}")
        return None
    except Exception as e:
        log.warning(f"reason=drEventParseException,e={e},payload={event_value!r}")
        return None
