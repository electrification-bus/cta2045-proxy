# Contributing to ekm-proxy

Thanks for your interest in contributing! `ekm-proxy` publishes [EKM Metering](https://www.ekmmetering.com/) devices (Omnimeters, and ioStack IO/sensor modules read by an EKM Push3 or over RS-485) onto the [Electrification Bus (eBus)](https://ebus.energy) as [Homie 5](https://homieiot.github.io) devices. It is an eBus **proxier** (see the eBus specification's `proxy.md`). Architecture: a shared core (EKM to eBus field mapping plus a Homie 5 emitter built on [`ebus-sdk`](https://github.com/electrification-bus/python-sdk)) with pluggable **sources**, so the deployment variants (cloud MQTT / HA discovery, readMeter API, RS-485 direct, future Push3-native) are just different backends.

## How to contribute

### Discussions

Use [Discussions](https://github.com/electrification-bus/ekm-proxy/discussions) for:

- Open-ended questions about the proxy's design, the source/emitter split, or how a new EKM field should map onto eBus capabilities.
- Proposed new sources (a new backend / transport for reading EKM data) or new deployment variants, worth aligning on shape before writing the code.
- Questions about the relationship between this proxy and the [Electrification Bus specification](https://github.com/electrification-bus/specification), especially the `energy.ebus.device.circuit` device type (behind-the-meter sub-metering as a `meter` capability on a host circuit) and the proxy convention (spec-level questions belong in the spec repo's Discussions).
- Thinking out loud about a proposed change before scoping it.

Discussions are open-ended, a good place to align on direction before something becomes a concrete change. Aligned outcomes often turn into one or more Issues or pull requests.

### Issues

Use [Issues](https://github.com/electrification-bus/ekm-proxy/issues) for actionable changes:

- Bug reports with reproduction steps (source variant, broker, a sample discovery or readMeter payload, code snippet).
- Field-mapping gaps or errors (an EKM field mapped to the wrong eBus capability/property/unit, or a field that should be mapped but is held).
- Spec-conformance gaps where the emitted eBus device diverges from the [Electrification Bus specification](https://github.com/electrification-bus/specification) (note which spec document and section).
- Concrete feature requests with a clear scope and a use case.
- Documentation gaps where a specific README, reference, or docstring change is intended.

If you're not sure whether something is an Issue or a Discussion, start with a Discussion; we can convert it later.

### Pull requests

Pull requests are welcome.

- For small fixes (typos, docstring tweaks, a mapping-table correction with a test, low-risk bug fixes with a test), open a PR directly.
- For substantive changes (a new source, changes to the `Source` / `Reading` interface, changes to the emitted device shape or the `energy.ebus.device.circuit` / `meter`-capability profile, new dependencies), open a Discussion or Issue first so we can align on scope before you invest the effort.
- **Spec conformance is the north star.** The emitted devices implement the [Electrification Bus specification](https://github.com/electrification-bus/specification). When a change is normative (device type, capability/property contract, units, topic structure), point to the spec section it implements. If the spec is ambiguous or wrong, file an Issue against the spec repo first and reference it from the PR here.
- **Respect the layer boundaries.** Pure MQTT transport concerns (TLS, reconnection, broker auth) belong in [`ebus-mqtt-client`](https://github.com/electrification-bus/ebus-mqtt-client); generic Homie 5 / eBus device semantics belong in [`ebus-sdk`](https://github.com/electrification-bus/python-sdk). This repo is the EKM-specific mapping plus the source variants on top of those.
- **Keep the HA discovery parser vendor-neutral.** `src/ekm_proxy/ha_discovery.py` is a general Home Assistant MQTT discovery parser with no EKM or eBus coupling, so it can be lifted into a shared library once a second proxy needs it. Do not add EKM-specific or eBus-specific logic there; put that in the mapping/emitter layers.
- **Lint before sending.** The repo enforces [ruff](https://github.com/astral-sh/ruff) via the [`Lint`](.github/workflows/lint.yml) workflow. Run `ruff check .` and `ruff format .` locally before pushing; CI will catch what you miss, but green-first is friendlier.
- **Tests are required.** New behavior needs a test (`pytest tests/`); bug fixes need a regression test. The [`Test`](.github/workflows/test.yml) workflow runs the suite on Python 3.10 and 3.12. Parser and mapping tests use synthetic fixtures (fake serials and names); do not add captured real device data to this repo.
- **Never commit secrets or captured device data.** Broker credentials, API keys, and live captures stay out of this public repo (they live in a private location). Secrets are provided at runtime via environment variables, never committed.
- **Keep comments to a minimum.** The project style is self-explanatory code, with comments reserved for non-obvious *why* (a spec quirk, an EKM firmware nuance, a Homie subtlety). Do not add comments that just restate the code.
- One commit per logical change is fine; we don't require squash or any particular branch naming.

## Code of conduct

Be respectful and constructive. We appreciate everyone who takes the time to file an issue, start a discussion, or send a pull request.

## Maintenance posture

`ekm-proxy` is an active alpha project. Updates and maintenance, including responses to issues filed on GitHub, will take place on an "as time and resources permit" basis. It is developed alongside [`ebus-sdk`](https://github.com/electrification-bus/python-sdk), [`ebus-mqtt-client`](https://github.com/electrification-bus/ebus-mqtt-client), and the [Electrification Bus specification](https://github.com/electrification-bus/specification); see the specification repo's README for the project's long-term governance context.
