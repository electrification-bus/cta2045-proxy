# cta2045-proxy

[![CI](https://github.com/electrification-bus/cta2045-proxy/actions/workflows/test.yml/badge.svg)](https://github.com/electrification-bus/cta2045-proxy/actions/workflows/test.yml)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Proxy a CTA-2045 (EcoPort) Smart Grid Device onto the [Electrification Bus](https://ebus.energy) (eBus / Homie 5), through a pluggable UCM backend.

> **Status: pre-alpha.** Scaffold in progress; the SkyCentrics backend is being brought up against a live UCM.

## What it does

A CTA-2045 appliance (an SGD, e.g. a water heater) speaks demand-response through a UCM. This service bridges that appliance onto eBus so any eBus/Homie 5 controller can read its telemetry and command demand-response events, published per the eBus [proxy](https://github.com/electrification-bus/specification/blob/main/data-models/proxy.md) and [water-heater](https://github.com/electrification-bus/specification/blob/main/data-models/water-heater.md) data models:

```
ebus/5/{MAC}/       energy.ebus.device.bridge        (the UCM)
ebus/5/{MAC}-wh01/  energy.ebus.device.water-heater  (the proxied appliance)
```

## Architecture

Three layers, cleanly separated:

- **`cta2045` (upstream lib)** - the CTA-2045 protocol codec and the abstract, vendor-neutral `cta2045.ucm.Ucm` interface. Pure, no I/O.
- **`cta2045_proxy.ucm`** - concrete UCM backends binding `Ucm` to a real transport. Variants differ ONLY here:
  - `skycentrics` - a SkyCentrics Ethernet UCM (US08C) reachable over MQTT. Ships today.
  - `native` - an own-UCM driving the CTA-2045 RS485 link layer directly, no vendor dongle. Reserved; blocked on `cta2045.link`.
- **`cta2045_proxy.mapping` + `.emitter`** - the CTA-2045 -> eBus water-heater data-model translation and the Homie adapter, shared across all backends. Built on ebus-sdk's declarative proxy layer (`PropertySpec` + `build_from_declarations`); see the SDK's `doc/building-a-proxy.md`.

## Install

```
pip install -e ".[dev]"
```

Requires Python 3.10+.

## Run

```
cp config/config.example.toml config/config.toml   # then edit
export EBUS_MQTT_PASS=...                           # secrets via env, never the file
cta2045-proxy --config config/config.toml
```

See [`config/config.example.toml`](config/config.example.toml) for the `[ucm]` backend selector and the `[ebus]` output broker. A downstream deployment customizes only the config; the code is deployment-neutral.

## Bring up a SkyCentrics UCM

[`tools/`](tools/) has helper scripts to discover a SkyCentrics Ethernet UCM on your LAN, point it at a broker, and confirm it is publishing (`ucm-discover`, `ucm-configure`, `ucm-watch`), plus a how-to for standing up a local test broker (via the sibling [`broker-quickstart`](https://github.com/electrification-bus/broker-quickstart) or a bare Mosquitto). See [`tools/README.md`](tools/README.md).

## Example: the published Homie tree

A live capture of what the proxy publishes for one SkyCentrics UCM (`84FEDC538C72`) feeding one water heater. The bridge is the UCM; its child is the proxied appliance:

```
ebus/5/
├── 84FEDC538C72/                     # bridge device (the UCM)
│   ├── $state = ready
│   ├── info/
│   │   ├── vendor-name = SkyCentrics
│   │   └── firmware-version = v2.2 (26 June 2026, 9:0:0)
│   └── connection/
│       ├── feeds-device-id = 84FEDC538C72-wh01
│       ├── feeds-device-type = energy.ebus.device.water-heater
│       ├── feeds-device-status = OK
│       └── last-seen = 2026-07-05T20:24:49Z
└── 84FEDC538C72-wh01/                # proxied device (the water heater / SGD)
    ├── $state = ready
    ├── info/
    │   └── fuel-type = (unset until the SGD reports it)
    ├── meter/
    │   ├── active-power = 0.0 W
    │   └── imported-energy = 733.0 Wh
    ├── soc/
    │   ├── soe = 0.0 Wh
    │   ├── total-energy-storage = 4500.0 Wh
    │   └── loadup-headroom = (unset)
    ├── dr/
    │   ├── dr-response = NONE
    │   ├── opted-out = false
    │   ├── event = (settable — publish a DR command to .../dr/event/set)
    │   └── active-event = {"mode": "NORMAL"}
    └── status/
        └── fault-state = OK
```

Send a demand-response command by publishing to the settable `event` property, e.g. a 10-minute shed:

```
mosquitto_pub -t 'ebus/5/84FEDC538C72-wh01/dr/event/set' -m '{"mode":"SHED","duration":600}'
```

The proxy encodes it to CTA-2045 and forwards it to the UCM (`devices/84FEDC538C72/ctl/shed`); the SGD's resulting state flows back to `dr/dr-response` (e.g. `CURTAILED`).

## Development

```
ruff check . && ruff format --check .
pytest tests/ -v
```

Optionally install the pre-commit hooks (ruff format + lint on every commit, mirroring CI):

```
pip install pre-commit && pre-commit install
```

CI (`.github/workflows/`) runs the same ruff checks and pytest on 3.10 / 3.12 for every push and PR.

## References

- [CTA-2045 protocol library (`cta2045`)](https://github.com/electrification-bus/python-cta2045)
- [`ebus-sdk` building-a-proxy guide](https://github.com/electrification-bus/python-sdk/blob/main/doc/building-a-proxy.md)
- [eBus specification](https://github.com/electrification-bus/specification)
