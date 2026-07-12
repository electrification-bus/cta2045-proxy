"""The adapter layer: Homie bridge+child tree mirrored from the observable model.

One `WaterHeaterProxyDevice` per discovered UCM. It builds the eBus topology

  ebus/5/{MAC}/       energy.ebus.device.bridge        (the UCM)
  ebus/5/{MAC}-wh01/  energy.ebus.device.water-heater  (the proxied appliance)

from the declarative `PropertySpec` tables in `mapping`, using ebus-sdk's
`build_from_declarations` (which creates each Homie node/property, the observable
`GroupedPropertyDict` twin, and the on-change binding between them in one call).
Acquisition code only ever calls `model.set_value(...)`; publishing to MQTT is an
automatic side-effect. See python-sdk `doc/building-a-proxy.md`.
"""

from __future__ import annotations

import logging
import time
from typing import Dict, Optional, Tuple

import ebus_sdk.homie as homie
from ebus_sdk import GroupedPropertyDict, build_from_declarations

from . import mapping


class WaterHeaterProxyDevice:
    """Per-MAC observable models + Homie tree for one UCM and its water heater."""

    def __init__(self, mac: str, ucm, ebus_cfg: dict, log: Optional[logging.Logger] = None):
        self._mac = mac
        self._ucm = ucm
        self._log = log or logging.getLogger(f"WaterHeaterProxyDevice[{mac}]")
        self._wh_id = f"{mac}-wh01"

        self.bridge_model = GroupedPropertyDict()
        self.wh_model = GroupedPropertyDict()

        # Bridge root owns the MQTT connection (and the Last Will); the child
        # shares it via parent=.
        self.bridge = homie.Device(
            id=mac,
            name=f"SkyCentrics UCM {mac}",
            type="energy.ebus.device.bridge",
            mqtt_cfg=ebus_cfg,
        )
        # ebus-sdk 0.8: Device(mqtt_cfg=) creates the client but does NOT start its
        # network loop. Start it and wait for the broker connection before the
        # first publish, or every property publish warns NoMqttClient and the
        # first retained $description/$state is a pre-connect snapshot.
        # (doc/building-a-proxy.md "Lifecycle and state".)
        self.bridge.start_mqtt_client()
        self._await_connected(self.bridge)
        self._bridge_props: Dict[Tuple[str, str], homie.Property] = build_from_declarations(
            self.bridge, self.bridge_model, mapping.BRIDGE_SPECS
        )

        self.water_heater = homie.Device(
            id=self._wh_id,
            name=f"Water Heater {self._wh_id}",
            type="energy.ebus.device.water-heater",
            parent=self.bridge,
        )
        # build_from_declarations (ebus-sdk >=0.9) wires the settable flex/request
        # inbound path from its spec's settable=True + entity_setter; no manual
        # post-build step is needed.
        self._wh_props: Dict[Tuple[str, str], homie.Property] = build_from_declarations(
            self.water_heater, self.wh_model, mapping.water_heater_specs(self._on_flex_request_set)
        )

        # Static bridge connection view: the UCM->water-heater link. Marked OK
        # until a heartbeat says otherwise.
        self.bridge_model.set_value("connection", "feeds-device-id", self._wh_id)
        self.bridge_model.set_value("connection", "feeds-device-type", "energy.ebus.device.water-heater")
        self.bridge_model.set_value("connection", "feeds-device-status", "OK")

        self._log.info(f"reason=deviceBuilt,mac={mac},whId={self._wh_id}")

    def _await_connected(self, device, timeout: float = 10.0) -> None:
        """Block until the device's MQTT client reports connected, or time out."""
        mqttc = device.mqttc
        if mqttc is None:
            self._log.warning(f"reason=noMqttClientToAwait,mac={self._mac}")
            return
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if mqttc.is_connected():
                self._log.info(f"reason=bridgeConnected,mac={self._mac}")
                return
            time.sleep(0.1)
        self._log.warning(f"reason=bridgeConnectTimeout,mac={self._mac},timeout={timeout}")

    # -- inbound (report) path ------------------------------------------- #

    def on_message(self, message) -> None:
        """Apply a decoded CTA-2045 message to the models (publishing follows)."""
        mapping.apply_decoded(message, self.bridge_model, self.wh_model, self._log)

    # Which bridge capability each UCM-reported property belongs to.
    _BRIDGE_PROP_CAP = {
        "vendor-name": "info",
        "firmware-version": "info",
        "last-seen": "connection",
    }

    def set_bridge_info(self, info: dict) -> None:
        """Populate bridge (UCM) properties from backend-sourced metadata.

        The UCM's own vendor/firmware (from the SkyCentrics devinfo JSON) and its
        last-seen heartbeat (from each /data timestamp) are independent of any
        attached SGD. Each key routes to its owning capability; unknown keys
        default to `info`.
        """
        for prop_id, value in info.items():
            if value is None:
                continue
            cap = self._BRIDGE_PROP_CAP.get(prop_id, "info")
            self.bridge_model.set_value(cap, prop_id, value)

    # -- outbound (control) path ----------------------------------------- #

    def _on_flex_request_set(self, request_value):
        """entity_setter for flex/request: validate, translate to CTA-2045, send to the UCM."""
        msg = mapping.command_for_flex_request(request_value, self._log)
        if msg is None:
            return request_value
        self._ucm.send(msg)
        # Echo the accepted request onto active-request for observers.
        self.wh_model.set_value("flex", "active-request", request_value)
        return request_value

    # -- lifecycle -------------------------------------------------------- #

    def cleanup(self) -> None:
        """Gracefully tear down the device tree.

        ebus-sdk 0.10's Device.stop() is a tree-level teardown: it publishes a
        final $state=disconnected for the bridge root (which, per the Homie 5
        effective-state rule, covers the child water-heater) then stops the
        shared MQTT client. It is bounded end-to-end, so a dead broker can't
        stall shutdown. This supersedes the old set-LOST-then-mqttc.stop() dance.
        """
        try:
            self.bridge.stop()
        except Exception as e:
            self._log.warning(f"reason=cleanupStopFail,mac={self._mac},e={e}")
