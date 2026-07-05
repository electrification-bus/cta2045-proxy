"""Core: wire a UCM backend to per-device emitters and run the lifecycle.

Backend discovers a UCM -> `_on_discover` builds its Homie tree; backend decodes
a message -> `_on_message` routes it to that device's emitter. The core is
transport- and vendor-agnostic: everything specific to SkyCentrics lives in the
selected `ucm` backend, everything specific to the water-heater data model lives
in `mapping`.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

from .broker import resolve_broker_cfg
from .emitter import WaterHeaterProxyDevice
from .ucm import build_backend


class Cta2045Proxy:
    def __init__(self, cfg: dict, log: Optional[logging.Logger] = None):
        self._cfg = cfg
        self._log = log or logging.getLogger("cta2045_proxy")

        # [ebus] is the Homie output broker. The UCM transport broker defaults to
        # the same connection (the SkyCentrics UCM shares the local broker), but
        # a backend section may override host/port/username.
        self._ebus_cfg = resolve_broker_cfg(cfg.get("ebus", {}))
        ucm_section = cfg.get("ucm", {}).get(cfg["ucm"]["kind"], {})
        self._ucm_broker_cfg = resolve_broker_cfg(ucm_section) if ucm_section.get("host") else self._ebus_cfg

        self._devices: Dict[str, WaterHeaterProxyDevice] = {}
        self._backend = build_backend(
            cfg,
            self._ucm_broker_cfg,
            self._on_discover,
            self._on_message,
            self._on_ucm_info,
            self._log,
        )

    def start(self) -> None:
        self._backend.start()
        self._log.info(f"reason=proxyStarted,ucm={self._cfg['ucm']['kind']}")

    def _on_discover(self, mac: str, ucm) -> None:
        if mac in self._devices:
            return
        self._log.info(f"reason=buildDevice,mac={mac}")
        self._devices[mac] = WaterHeaterProxyDevice(
            mac=mac,
            ucm=ucm,
            ebus_cfg=self._ebus_cfg,
            log=logging.getLogger(f"WaterHeaterProxyDevice[{mac}]"),
        )

    def _on_message(self, mac: str, message) -> None:
        device = self._devices.get(mac)
        if device is None:
            self._log.warning(f"reason=messageNoDevice,mac={mac}")
            return
        device.on_message(message)

    def _on_ucm_info(self, mac: str, info: dict) -> None:
        """Backend-sourced UCM metadata (vendor, firmware) for the bridge info."""
        device = self._devices.get(mac)
        if device is None:
            self._log.warning(f"reason=ucmInfoNoDevice,mac={mac}")
            return
        device.set_bridge_info(info)

    def stop(self) -> None:
        self._log.info("reason=proxyStopping")
        for device in list(self._devices.values()):
            device.cleanup()
        self._backend.stop()
