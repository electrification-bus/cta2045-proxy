"""SkyCentrics Ethernet UCM backend (MQTT transport).

A SkyCentrics Ethernet UCM (model US08C) is provisioned to point its MQTT client
at a local broker and speaks CTA-2045 frames as ASCII-hex JSON on per-device
topics:

Inbound (UCM -> broker):
  devices/{MAC}/data       JSON {"t": <unix>, "d": "<ascii-hex>"}  telemetry
  devices/{MAC}/devinfo    JSON {"SGD": {"d": "<ascii-hex>"}, ...} device info

Outbound (broker -> UCM):
  devices/{MAC}/ctl/shed   JSON {"d": "<ascii-hex>"}  Shed/End/Critical-Peak/Grid-Emergency
  devices/{MAC}/ctl/event  JSON {"d": "<ascii-hex>"}  Load-Up/Advanced-Load-Up/queries

There is NO SkyCentrics cloud broker in the loop: the UCM connects directly to
the same local broker this backend uses. `{MAC}` is the 12-char uppercase-hex
MAC verbatim (it becomes the Homie bridge device-id upstream).
"""

from __future__ import annotations

import datetime
import json
import logging
import re
from typing import Callable, Dict, Optional

import cta2045
from cta2045.enums import BasicDRCategory
from cta2045.ucm import Ucm

from ebus_mqtt_client import MqttClient

# Topic patterns the UCM uses on the broker.
_TOPIC_DATA = re.compile(r"^devices/([0-9A-F]{12})/data$")
_TOPIC_DEVINFO = re.compile(r"^devices/([0-9A-F]{12})/devinfo$")


def _unix_to_iso(ts) -> Optional[str]:
    """Convert a Unix-epoch-seconds value (int or str) to an ISO-8601 UTC string."""
    if ts is None:
        return None
    try:
        return datetime.datetime.fromtimestamp(int(ts), tz=datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, TypeError, OSError, OverflowError):
        return None


class _SkyCentricsUcm(Ucm):
    """Concrete `Ucm` binding for one SkyCentrics UCM at a given MAC.

    `transmit()` publishes an outbound CTA-2045 frame to the UCM's control
    topic; `on_message()` hands each decoded inbound message to the backend.
    """

    def __init__(self, mac: str, backend: "SkyCentricsUcmBackend"):
        super().__init__()
        self._mac = mac
        self._backend = backend
        self._logger = logging.getLogger(f"SkyCentricsUcm[{mac}]")

    def transmit(self, frame: bytes) -> None:
        """Publish a CTA-2045 frame as ASCII-hex JSON to the UCM.

        Route shed-class basic-DR opcodes to /ctl/shed (matching the SkyCentrics
        topic split) and everything else to /ctl/event. Frame layout:
        msb, lsb, len_hi, len_lo, opcode, ...
        """
        is_basic_dr = len(frame) >= 5 and frame[0] == 0x08 and frame[1] == 0x01
        opcode = frame[4] if is_basic_dr else None
        is_shed_class = opcode in (
            BasicDRCategory.Shed.value,
            BasicDRCategory.End_Shed.value,
            BasicDRCategory.Critical_Peak_Event.value,
            BasicDRCategory.Grid_Emergency.value,
        )
        suffix = "shed" if is_shed_class else "event"

        topic = f"devices/{self._mac}/ctl/{suffix}"
        payload = json.dumps({"d": cta2045.codec.bytes_to_hex(frame)})
        self._logger.info(f"reason=ucmTransmit,topic={topic},len={len(frame)}")
        self._backend.publish(topic, payload)

    def on_message(self, message) -> None:
        self._logger.debug(f"reason=ucmOnMessage,type={type(message).__name__}")
        self._backend.deliver(self._mac, message)


class SkyCentricsUcmBackend:
    """Owns the MQTT client to the UCM topics and the per-MAC UCM fleet.

    On the first sighting of a MAC it lazily creates a `_SkyCentricsUcm` and
    calls `on_discover(mac, ucm)` so the core can build that UCM's Homie tree;
    each decoded message is delivered via `on_message(mac, message)`.
    """

    def __init__(
        self,
        cfg: dict,
        broker_cfg: dict,
        on_discover: Callable,
        on_message: Callable,
        on_ucm_info: Callable,
        log: Optional[logging.Logger] = None,
    ):
        self._cfg = cfg
        self._broker_cfg = broker_cfg
        self._on_discover = on_discover
        self._on_message = on_message
        self._on_ucm_info = on_ucm_info
        self._logger = log or logging.getLogger("SkyCentricsUcmBackend")
        self._mqtt: Optional[MqttClient] = None
        self._ucms: Dict[str, _SkyCentricsUcm] = {}

    def start(self) -> None:
        self._mqtt = MqttClient.from_config(
            mqtt_cfg=self._broker_cfg,
            client_id=self._cfg.get("client_id", "cta2045-proxy-ucm"),
        )
        self._mqtt.start(blocking=False)
        # ebus-mqtt-client invokes each subscription's callback as (topic, payload).
        self._mqtt.subscribe("devices/+/data", self._on_data_msg)
        self._mqtt.subscribe("devices/+/devinfo", self._on_devinfo_msg)
        self._logger.info("reason=skycentricsBackendStarted,subscriptions=2")

    def publish(self, topic: str, payload: str, retain: bool = False) -> None:
        if self._mqtt is None:
            self._logger.error(f"reason=publishNoClient,topic={topic}")
            return
        self._mqtt.publish(topic, payload, retain=retain)

    def deliver(self, mac: str, message) -> None:
        """Forward a decoded message from a per-MAC UCM up to the core."""
        self._on_message(mac, message)

    def stop(self) -> None:
        if self._mqtt is not None:
            try:
                self._mqtt.stop()
            except Exception as e:
                self._logger.warning(f"reason=backendMqttStopFail,e={e}")

    # -- inbound topic handlers ------------------------------------------- #

    def _on_data_msg(self, topic: str, payload: bytes) -> None:
        m = _TOPIC_DATA.match(topic)
        if not m:
            self._logger.warning(f"reason=dataTopicMatchFail,topic={topic}")
            return
        self._handle_data(m.group(1), payload)

    def _on_devinfo_msg(self, topic: str, payload: bytes) -> None:
        m = _TOPIC_DEVINFO.match(topic)
        if not m:
            self._logger.warning(f"reason=devinfoTopicMatchFail,topic={topic}")
            return
        self._handle_devinfo(m.group(1), payload)

    def _handle_data(self, mac: str, payload: bytes) -> None:
        try:
            env = json.loads(payload)
            hex_str = env["d"]
        except (ValueError, KeyError, TypeError) as e:
            self._logger.warning(f"reason=dataParseFail,mac={mac},e={e}")
            return
        ucm = self._ucm_for(mac)
        # The UCM stamps every /data with a Unix-epoch "t" (its report clock,
        # present even on empty keepalives). Surface it as the bridge's last-seen
        # heartbeat: an ISO-8601 UTC liveness/freshness signal.
        iso = _unix_to_iso(env.get("t"))
        if iso:
            self._on_ucm_info(mac, {"last-seen": iso})
        # The SkyCentrics UCM firmware prepends one garbage byte to /data (not to
        # /devinfo); documented in the legacy ecoport-experiments demo.
        raw = cta2045.codec.hex_to_bytes(hex_str)
        try:
            ucm.receive(raw[1:])
        except Exception as e:
            self._logger.warning(f"reason=dataDecodeFail,mac={mac},e={e}")

    def _handle_devinfo(self, mac: str, payload: bytes) -> None:
        # Observed envelope: {"UCM": {"version": ..., "build": ..., "SGD":
        # {"d": "<hex>"}}}. Tolerate a flat {"SGD": {"d": ...}} too.
        try:
            env = json.loads(payload)
        except (ValueError, TypeError) as e:
            self._logger.warning(f"reason=devinfoParseFail,mac={mac},e={e}")
            return
        ucm_block = env.get("UCM", env) if isinstance(env, dict) else {}

        # Ensure the device exists, then publish the UCM's own (bridge) metadata
        # straight from the JSON — available even when no SGD is attached.
        self._ucm_for(mac)
        version = ucm_block.get("version")
        build = (ucm_block.get("build") or "").strip()
        if version or build:
            fw = f"{version} ({build})" if version and build else (version or build)
            self._on_ucm_info(mac, {"vendor-name": "SkyCentrics", "firmware-version": fw})

        # SGD (appliance) info via CTA-2045, when present. `d` is empty when the
        # UCM has no attached SGD to report; treat that as a no-op, not a failure.
        sgd = ucm_block.get("SGD", {}) if isinstance(ucm_block, dict) else {}
        hex_str = sgd.get("d", "") if isinstance(sgd, dict) else ""
        if not hex_str:
            self._logger.debug(f"reason=devinfoNoSgd,mac={mac}")
            return
        raw = cta2045.codec.hex_to_bytes(hex_str)
        ucm = self._ucm_for(mac)
        try:
            ucm.receive(raw)
        except Exception as e:
            self._logger.warning(f"reason=devinfoDecodeFail,mac={mac},e={e}")

    def _ucm_for(self, mac: str) -> _SkyCentricsUcm:
        """Lazily create the UCM (and announce it) the first time a MAC is seen."""
        ucm = self._ucms.get(mac)
        if ucm is None:
            self._logger.info(f"reason=discoverUcm,mac={mac}")
            ucm = _SkyCentricsUcm(mac, self)
            self._ucms[mac] = ucm
            self._on_discover(mac, ucm)
        return ucm
