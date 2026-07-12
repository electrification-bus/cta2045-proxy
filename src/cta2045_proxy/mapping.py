"""CTA-2045 semantics <-> eBus water-heater data model.

Pure translation: no MQTT, no Homie devices. This module owns

- the declarative `PropertySpec` tables for the bridge (UCM) root device and
  the proxied water-heater child (the single source of truth that
  `ebus_sdk.build_from_declarations` materializes into both the observable
  model and the Homie tree), and
- the decode-direction handlers that turn a decoded `cta2045.app` message into
  observable-model updates, plus the encode-direction translation of a Homie
  `flex/request` command back into a CTA-2045 application message.

Capability reference: ../../specification/capabilities/flex.md (the `flex`
control-and-feedback surface); data-model reference:
../../specification/data-models/water-heater.md (§Example: CTA-2045 water
heater). Built against ebus-sdk's declarative proxy layer (PropertySpec +
build_from_declarations) and its json `$format` JSONSchema validation.
"""

from __future__ import annotations

import json
import logging
from typing import Callable, Optional

from cta2045 import app
from cta2045.enums import AdvancedLoadUpUnits, CommodityCode, OperationalState

from ebus_sdk import PropertyDatatype, PropertySpec, Unit, validate_json_format

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
    PropertySpec("connection", "feeds-device-status", PropertyDatatype.ENUM, format="OK,LOST,DEGRADED"),
    # last-seen: the UCM's own report timestamp (from the SkyCentrics /data "t"
    # field), as an ISO-8601 UTC datetime. Not part of the eBus data model; a
    # liveness/freshness heartbeat, updated on every message the UCM sends.
    PropertySpec("connection", "last-seen", PropertyDatatype.DATETIME),
]


# The `flex/request` control surface this device accepts, as a JSONSchema (the
# Homie 5 json `$format`, capabilities/flex.md §Self-describing control surface).
# The schema IS the exact accepted surface (additionalProperties is false), so a
# controller reads it and sends only what it permits:
#   - mode + intensity: the CTA-2045 Basic / Advanced DR command set.
#   - duration: request length in seconds (absent = until changed).
#   - cause: advisory (Matter AdjustmentCauseEnum). CTA-2045 cannot enforce a
#     directional opt-out, so it is not acted on, only carried to active-request.
#   - target-percentage: the LOAD_UP thermal refinement (Matter Boost) -> heat
#     until stored-energy `soc` reaches this %. Encoded as CTA-2045 Advanced Load
#     Up (requires mode LOAD_UP + intensity ADVANCED).
# `level` is OMITTED: a CTA-2045 SGD sheds / loads up without a percentage.
# `temporary-setpoint` is OMITTED: CTA-2045 Advanced Load Up quantifies energy in
# watt-hours (AdvancedLoadUpUnits) and cannot express a temperature target.
FLEX_REQUEST_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "mode": {"enum": ["SHED", "LOAD_UP", "NORMAL"]},
        "intensity": {"enum": ["PEAK", "EMERGENCY", "ADVANCED"]},
        "duration": {"type": "integer", "minimum": 0},
        "cause": {"enum": ["LOCAL_OPTIMIZATION", "GRID_OPTIMIZATION"]},
        "target-percentage": {"type": "integer", "minimum": 0, "maximum": 100},
    },
    "required": ["mode"],
    "additionalProperties": False,
}
# Homie wire form of the schema (the `$format` string on the request property).
FLEX_REQUEST_FORMAT: str = json.dumps(FLEX_REQUEST_SCHEMA, separators=(",", ":"))


# --- Declarative schema: the proxied water-heater child ----------------------
# A factory rather than a module constant: the settable `flex/request` property's
# entity_setter is a per-device bound method (it needs the device's UCM + model),
# so it must be supplied at build time. build_from_declarations (ebus-sdk >=0.9)
# wires the whole inbound /set path from settable=True + entity_setter.
def water_heater_specs(on_flex_request_set: Callable) -> list[PropertySpec]:
    """PropertySpecs for the water-heater child, with flex/request bound to its setter."""
    return [
        PropertySpec("info", "fuel-type", PropertyDatatype.ENUM, format="ELECTRIC,GAS,HEAT_PUMP,HYBRID,OTHER"),
        PropertySpec("meter", "active-power", PropertyDatatype.FLOAT, Unit.WATT),
        PropertySpec("meter", "imported-energy", PropertyDatatype.FLOAT, Unit.WATT_HOUR),
        PropertySpec("soc", "soe", PropertyDatatype.FLOAT, Unit.WATT_HOUR),
        PropertySpec("soc", "total-energy-storage", PropertyDatatype.FLOAT, Unit.WATT_HOUR),
        PropertySpec("soc", "loadup-headroom", PropertyDatatype.FLOAT, Unit.WATT_HOUR),
        # response: decomposed vendor-neutral state (replaces CTA-2045's 15-value
        # operational-state enum). opt-out: four-way Matter OptOutStateEnum; a
        # CTA-2045 device models only the on/off "Grid Enabled" override, so it
        # uses NONE and ALL (ALL when Grid Enabled is off).
        PropertySpec("flex", "response", PropertyDatatype.ENUM, format="NONE,CURTAILED,BOOSTED,NOT_FOLLOWING"),
        PropertySpec("flex", "opt-out", PropertyDatatype.ENUM, format="NONE,LOCAL,GRID,ALL"),
        # Settable (controller -> device): an arriving /set routes through the
        # model to on_flex_request_set, which validates it against the request
        # $format and translates it to a CTA-2045 command. The $format advertises
        # this device's accepted control surface.
        PropertySpec(
            "flex",
            "request",
            PropertyDatatype.JSON,
            settable=True,
            format=FLEX_REQUEST_FORMAT,
            entity_setter=on_flex_request_set,
        ),
        PropertySpec("flex", "active-request", PropertyDatatype.JSON),
        PropertySpec("status", "fault-state", PropertyDatatype.ENUM, format="OK,FAULT,UNKNOWN"),
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
    response, opted_out, fault = OP_STATE_DECOMPOSITION.get(state, ("NONE", False, False))
    wh.set_value("flex", "response", response)
    # CTA-2045 has only a single on/off opt-out (the "Grid Enabled" override), so
    # it maps to the four-way flex/opt-out as ALL (off) or NONE (participating);
    # there is no LOCAL/GRID split at this layer.
    wh.set_value("flex", "opt-out", "ALL" if opted_out else "NONE")
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


# --- Encode direction: Homie flex/request command -> CTA-2045 message --------


def _quantize_load_up_wh(extra_wh: float) -> tuple:
    """Pick a CTA-2045 Advanced Load Up (value, units) for `extra_wh` watt-hours.

    Advanced Load Up carries `value x units` Wh in a 2-byte value (CTA-2045-B
    § 11.6.3), so choose the finest Wh unit whose quantized value fits in 16 bits.
    Returns (value:int, units:AdvancedLoadUpUnits).
    """
    for units in (
        AdvancedLoadUpUnits.Wh_1,
        AdvancedLoadUpUnits.Wh_10,
        AdvancedLoadUpUnits.Wh_100,
        AdvancedLoadUpUnits.Wh_1000,
    ):
        scale = 10**units.value  # Wh_1->1, Wh_10->10, Wh_100->100, Wh_1000->1000
        value = round(extra_wh / scale)
        if value <= 0xFFFF:
            return max(0, value), units
    return 0xFFFF, AdvancedLoadUpUnits.Wh_1000


def command_for_flex_request(
    request_value,
    log: Optional[logging.Logger] = None,
    *,
    capacity_wh: Optional[float] = None,
    current_wh: Optional[float] = None,
):
    """Translate a `flex/request` JSON object into a CTA-2045 application message.

    Returns a `cta2045.app` message ready for `Ucm.send`, or None if the request
    is invalid against the request `$format` or could not be translated (unknown
    mode / parse failure). The caller owns the transport; this function is pure.

    `capacity_wh` (the device's total energy storage) and `current_wh` (its
    present stored energy, `soc/soe`) let a `LOAD_UP` + `ADVANCED` request with a
    `target-percentage` be encoded as CTA-2045 Advanced Load Up: the command
    carries the *extra* Wh to store, so the absolute soc target is turned into
    `(target%/100) * capacity - current`. When either is unknown, the request
    falls back to Basic DR load-up.
    """
    log = log or logging.getLogger("cta2045_proxy.mapping")
    try:
        evt = json.loads(request_value) if isinstance(request_value, (str, bytes)) else request_value
        # Reject commands the advertised control surface does not permit, so a
        # malformed or out-of-surface /set never reaches the CTA-2045 link.
        err = validate_json_format(evt, FLEX_REQUEST_SCHEMA)
        if err:
            log.warning(f"reason=flexRequestInvalid,err={err},payload={request_value!r}")
            return None
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
            target_pct = evt.get("target-percentage")
            # Advanced Load Up (a Wh energy target) applies only when the caller
            # asked for ADVANCED intensity AND gave a target-percentage, and the
            # device has reported the capacity + current stored energy needed to
            # turn that absolute soc target into the "extra" Wh the command
            # carries. Otherwise fall back to Basic DR load-up.
            if intensity == "ADVANCED" and target_pct is not None and capacity_wh and current_wh is not None:
                target_wh = (target_pct / 100.0) * capacity_wh
                extra_wh = max(0.0, target_wh - current_wh)
                value, units = _quantize_load_up_wh(extra_wh)
                duration_minutes = int(round(duration_min)) if duration_min is not None else 0
                return app.advanced_load_up(duration_minutes, value, units)
            if intensity == "ADVANCED" and target_pct is not None:
                log.info(
                    "reason=advancedLoadUpNeedsSoc,"
                    f"capacityKnown={capacity_wh is not None},currentKnown={current_wh is not None}"
                )
            return app.load_up(duration_min)

        log.warning(f"reason=flexRequestUnknownMode,mode={mode}")
        return None
    except Exception as e:
        log.warning(f"reason=flexRequestParseException,e={e},payload={request_value!r}")
        return None
