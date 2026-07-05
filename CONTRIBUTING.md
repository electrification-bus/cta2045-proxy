# Contributing to cta2045-proxy

Thanks for your interest in contributing! `cta2045-proxy` publishes a [CTA-2045](https://en.wikipedia.org/wiki/CTA-2045) (EcoPort) Smart Grid Device (an SGD, e.g. a water heater) onto the [Electrification Bus (eBus)](https://ebus.energy) as [Homie 5](https://homieiot.github.io) devices. It is an eBus **proxier** (see the eBus specification's `proxy.md`). Architecture: a shared core (CTA-2045 to eBus water-heater mapping plus a Homie 5 emitter built on [`ebus-sdk`](https://github.com/electrification-bus/python-sdk)) with pluggable **UCM backends**, so the transport variants (a SkyCentrics Ethernet UCM over MQTT today, a native RS485 own-UCM later) are just different backends behind the vendor-neutral `cta2045.ucm.Ucm` interface.

## How to contribute

### Discussions

Use [Discussions](https://github.com/electrification-bus/cta2045-proxy/discussions) for:

- Open-ended questions about the proxy's design, the UCM-backend / emitter split, or how a CTA-2045 message should map onto eBus capabilities.
- Proposed new UCM backends (a new transport binding of `cta2045.ucm.Ucm`) or new proxied device types, worth aligning on shape before writing the code.
- Questions about the relationship between this proxy and the [Electrification Bus specification](https://github.com/electrification-bus/specification), especially the water-heater data model and the proxy convention (spec-level questions belong in the spec repo's Discussions).
- Thinking out loud about a proposed change before scoping it.

Discussions are open-ended, a good place to align on direction before something becomes a concrete change. Aligned outcomes often turn into one or more Issues or pull requests.

### Issues

Use [Issues](https://github.com/electrification-bus/cta2045-proxy/issues) for actionable changes:

- Bug reports with reproduction steps (UCM backend, broker, a sample `/data` or `/devinfo` payload, code snippet).
- Mapping gaps or errors (a CTA-2045 field mapped to the wrong eBus capability/property/unit, or a field that should be mapped but is held).
- Spec-conformance gaps where the emitted eBus device diverges from the [Electrification Bus specification](https://github.com/electrification-bus/specification) (note which spec document and section).
- Concrete feature requests with a clear scope and a use case.
- Documentation gaps where a specific README, reference, or docstring change is intended.

If you're not sure whether something is an Issue or a Discussion, start with a Discussion; we can convert it later.

### Pull requests

Pull requests are welcome.

- For small fixes (typos, docstring tweaks, a mapping-table correction with a test, low-risk bug fixes with a test), open a PR directly.
- For substantive changes (a new UCM backend, changes to how the proxy uses the `cta2045.ucm.Ucm` interface, changes to the emitted device shape or the water-heater capability profile, new dependencies), open a Discussion or Issue first so we can align on scope before you invest the effort.
- **Spec conformance is the north star.** The emitted devices implement the [Electrification Bus specification](https://github.com/electrification-bus/specification). When a change is normative (device type, capability/property contract, units, topic structure), point to the spec section it implements. If the spec is ambiguous or wrong, file an Issue against the spec repo first and reference it from the PR here.
- **Respect the layer boundaries.** The CTA-2045 message layer (encode/decode, the abstract UCM interface) belongs in [`cta2045`](https://github.com/electrification-bus/python-cta2045); pure MQTT transport concerns (TLS, reconnection, broker auth) belong in [`ebus-mqtt-client`](https://github.com/electrification-bus/ebus-mqtt-client); generic Homie 5 / eBus device semantics belong in [`ebus-sdk`](https://github.com/electrification-bus/python-sdk). This repo is the concrete UCM backends plus the CTA-2045 to eBus mapping on top of those.
- **Keep UCM backends behind the `Ucm` interface.** A backend binds `cta2045.ucm.Ucm` to a transport and delivers decoded CTA-2045 messages upward; it should not reach into the mapping or Homie layers. Vendor-specific parsing (a dongle's JSON envelope, a serial framing) lives in the backend; the CTA-2045 to eBus mapping stays vendor-neutral in `mapping.py`.
- **Lint before sending.** The repo enforces [ruff](https://github.com/astral-sh/ruff) via the [`Lint`](.github/workflows/lint.yml) workflow. Run `ruff check .` and `ruff format .` locally before pushing; CI will catch what you miss, but green-first is friendlier.
- **Tests are required.** New behavior needs a test (`pytest tests/`); bug fixes need a regression test. The [`Test`](.github/workflows/test.yml) workflow runs the suite on Python 3.10 and 3.12. Codec and mapping tests use synthetic fixtures (fabricated MACs and frames); do not add captured real device data to this repo.
- **Never commit secrets or captured device data.** Broker credentials, UCM credentials, and live captures stay out of this public repo (they live in a private location). Secrets are provided at runtime via environment variables, never committed.
- **Keep comments to a minimum.** The project style is self-explanatory code, with comments reserved for non-obvious *why* (a CTA-2045 spec quirk, a UCM firmware nuance, a Homie subtlety). Do not add comments that just restate the code.
- One commit per logical change is fine; we don't require squash or any particular branch naming.

## Code of conduct

Be respectful and constructive. We appreciate everyone who takes the time to file an issue, start a discussion, or send a pull request.

## Maintenance posture

`cta2045-proxy` is an active pre-alpha project. Updates and maintenance, including responses to issues filed on GitHub, will take place on an "as time and resources permit" basis. It is developed alongside [`cta2045`](https://github.com/electrification-bus/python-cta2045), [`ebus-sdk`](https://github.com/electrification-bus/python-sdk), [`ebus-mqtt-client`](https://github.com/electrification-bus/ebus-mqtt-client), and the [Electrification Bus specification](https://github.com/electrification-bus/specification); see the specification repo's README for the project's long-term governance context.
