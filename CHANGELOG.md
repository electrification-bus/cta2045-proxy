# Changelog

All notable changes to `cta2045-proxy` are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **Breaking (topic tree):** the demand-response capability the water-heater child publishes was renamed from `dr` to `flex`, tracking the eBus specification's rename of `energy.ebus.capability.dr` to the canonical `energy.ebus.capability.flex` ([`capabilities/flex.md`](https://github.com/electrification-bus/specification/blob/main/capabilities/flex.md)). Property renames: `dr/event` to `flex/request` (settable json), `dr/active-event` to `flex/active-request`, `dr/dr-response` to `flex/response`. `dr/opted-out` (boolean) becomes `flex/opt-out`, now a four-way enum (`NONE` / `LOCAL` / `GRID` / `ALL`); a CTA-2045 SGD models only the on/off "Grid Enabled" override, mapped to `ALL` (off) or `NONE`. `response` and `opt-out` are now Homie `enum` properties carrying their allowed-value lists. Consumers subscribed to the old `dr/*` topics must move to `flex/*`.

### Added

- The settable `flex/request` property advertises this device's accepted control surface in its Homie 5 `$format` JSONSchema (constraining `mode` and `intensity`, omitting `level` for a CTA-2045 SGD). Each inbound `/set` is validated against that schema (via ebus-sdk 0.11's `validate_json_format`) before translation, so an out-of-surface or malformed command never reaches the CTA-2045 link. The `ebus-sdk[validation]` extra (jsonschema) is now a dependency, and the floor is raised to `ebus-sdk>=0.11.0`.
- `flex/request` now accepts the Matter-aligned refinements: an advisory `cause` (`LOCAL_OPTIMIZATION` / `GRID_OPTIMIZATION`, carried through to `active-request`; CTA-2045 cannot enforce a directional opt-out) and, for load-up, a `target-percentage` that is encoded as CTA-2045 Advanced Load Up. Because Advanced Load Up carries the *extra* watt-hours to store, the absolute soc target is converted using the device's reported `soc/total-energy-storage` and `soc/soe` (`(target% / 100) * capacity - current`), falling back to Basic DR load-up when either is not yet known. The request `$format` is now strict (`additionalProperties: false`): `temporary-setpoint` is deliberately omitted, since Advanced Load Up quantifies energy in watt-hours and cannot express a temperature target (CTAP-52k).

## [0.1.2]

### Added

- The SkyCentrics UCM commissioning helpers (`tools/ucm-discover`, `tools/ucm-configure`, `tools/ucm-watch`) now ship in the **source distribution** via `MANIFEST.in`. They are deliberately kept **out of the installed wheel**: they are specific to the `skycentrics` backend (OUI scan, the SkyCentrics web UI, SkyCentrics topics), not general UCM tooling, so `pip install cta2045-proxy` adds nothing to your PATH. A downstream that runs the skycentrics backend installs them from the unpacked sdist as needed.

## [0.1.1]

### Fixed

- Legacy-setuptools packaging: added a `setup.py` shim so setuptools < 61 (notably the 59.5.0 pinned in Yocto kirkstone) builds a populated wheel from the sdist. Without it, the legacy build could not read `[tool.setuptools.packages.find]` or `[project.scripts]` from `pyproject.toml` and produced a wheel with the correct name and version but zero modules and no `cta2045-proxy` entry point (on a target image this left the module un-importable and `/usr/bin/cta2045-proxy` missing). Mirrors the `python-cta2045` shim. No API or behavior change.

## [0.1.0]

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
