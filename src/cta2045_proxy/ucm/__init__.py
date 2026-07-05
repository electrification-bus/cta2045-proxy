"""Pluggable UCM backends.

Each backend binds the abstract `cta2045.ucm.Ucm` to a real transport, discovers
the UCM(s) it can reach, and delivers decoded CTA-2045 messages upward. Variants
differ ONLY here; the mapping and emitter layers are shared (mirrors the
`sources/` pattern in the sibling ekm-proxy).

- `skycentrics`: a SkyCentrics Ethernet UCM reachable over MQTT (ships today).
- `native`: an own-UCM driving the CTA-2045 RS485 link layer directly, no vendor
  dongle (reserved; blocked on `cta2045.link` being implemented upstream).

A backend is constructed with two callbacks:
- `on_discover(mac, ucm)`: a UCM appeared; the core builds its emitter/Homie tree.
- `on_message(mac, message)`: a decoded CTA-2045 message arrived from that UCM.
"""

from __future__ import annotations

from typing import Callable, Optional

from cta2045.ucm import Ucm  # re-export the abstract, vendor-neutral interface

__all__ = ["Ucm", "build_backend"]


def build_backend(
    cfg: dict,
    broker_cfg: dict,
    on_discover: Callable,
    on_message: Callable,
    on_ucm_info: Callable,
    log: Optional["object"] = None,
):
    """Construct the UCM backend named by `cfg["ucm"]["kind"]`.

    `broker_cfg` is the resolved MQTT connection the backend should use to reach
    the UCM transport (for skycentrics this is the same local broker as `[ebus]`).
    `on_ucm_info(mac, info)` delivers backend-sourced UCM metadata (vendor,
    firmware) for the bridge's info capability, independent of any attached SGD.
    Lazy per-backend imports keep optional transport deps (e.g. pyserial for
    native) out of the import path unless selected.
    """
    kind = cfg["ucm"]["kind"]
    if kind == "skycentrics":
        from .skycentrics import SkyCentricsUcmBackend

        return SkyCentricsUcmBackend(
            cfg["ucm"].get("skycentrics", {}), broker_cfg, on_discover, on_message, on_ucm_info, log
        )
    if kind == "native":
        from .native import NativeUcmBackend

        return NativeUcmBackend(cfg["ucm"].get("native", {}), on_discover, on_message, on_ucm_info, log)
    raise ValueError(f"unknown ucm kind: {kind!r}")
