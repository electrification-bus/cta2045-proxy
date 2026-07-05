# Changelog

All notable changes to `cta2045-proxy` are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Initial (pre-alpha) release: proxy a CTA-2045 (EcoPort) Smart Grid Device onto the Electrification Bus (eBus / Homie 5) through a pluggable UCM backend.

### Added

- Three-layer architecture over the `cta2045` protocol library: pluggable UCM backends (`cta2045_proxy.ucm`), a transport-neutral CTA-2045 to eBus water-heater mapping (`mapping.py`), and a Homie adapter (`emitter.py`) built on ebus-sdk 0.8's declarative proxy layer (`PropertySpec` + `build_from_declarations`).
- `skycentrics` UCM backend: bridges a SkyCentrics Ethernet UCM (US08C) that connects to a local MQTT broker on `devices/{MAC}/...`. Decodes telemetry (`/data`, `/devinfo`) and encodes demand-response control (`/ctl/shed`, `/ctl/event`). No cloud broker in the loop.
- `native` UCM backend reserved: an own-UCM driving the CTA-2045 RS485 link layer directly (no vendor dongle), blocked on `cta2045.link` landing upstream in `python-cta2045`.
- Device topology per the eBus proxy convention: a bridge root (`energy.ebus.device.bridge`, the UCM) plus a proxied water-heater child (`energy.ebus.device.water-heater`, `{MAC}-wh01`).
- Bidirectional control: the settable `dr/event` (JSON) property translates NORMAL / SHED / LOAD_UP commands (with EMERGENCY and PEAK intensities) into CTA-2045 end / shed / load-up / grid-emergency / critical-peak frames sent to the UCM.
- Bridge `info` capability populated from the UCM's devinfo JSON (`vendor-name`, `firmware-version`), independent of any attached SGD.
- `connection/last-seen`: an ISO-8601 UTC heartbeat derived from the UCM's per-message timestamp. Not part of the eBus data model; a liveness/freshness signal published on every message the UCM sends.
- `tools/`: `ucm-discover` (find a UCM on the LAN by MAC OUI), `ucm-configure` (point a UCM at a broker via its web UI), and `ucm-watch` (tail a UCM's raw MQTT traffic), plus a local-broker how-to. macOS (bash 3.2) and Linux compatible.
- TOML configuration with a `[ucm]` backend selector and an `[ebus]` output broker; secrets come from the environment. A downstream deployment customizes only the config.

### Notes

- Validated end to end against a live SkyCentrics Ethernet UCM: telemetry decode, the full Homie tree, and the bidirectional control loop (a shed command reached the SGD, which entered CURTAILED and reported back).
- The settable `dr/event` property's inbound `/set` path is wired declaratively via `PropertySpec(settable=True, entity_setter=...)` (ebus-sdk 0.9's `build_from_declarations`).
