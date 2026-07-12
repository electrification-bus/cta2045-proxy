"""cta2045-proxy: bridge a CTA-2045 Smart Grid Device onto eBus / Homie 5.

Layering (see python-sdk `doc/building-a-proxy.md`):

- `cta2045` (upstream lib): the CTA-2045 protocol codec plus the abstract,
  vendor-neutral `cta2045.ucm.Ucm` interface. Pure, no I/O.
- `cta2045_proxy.ucm`: concrete UCM backends that bind `Ucm` to a real
  transport. `skycentrics` (a SkyCentrics Ethernet UCM over MQTT) ships today;
  `native` (RS485 own-UCM over `cta2045.link`) is reserved.
- `cta2045_proxy.mapping`: CTA-2045 semantics -> eBus water-heater data model
  (`PropertySpec` tables + decoded-message handlers). Pure of MQTT.
- `cta2045_proxy.emitter`: builds the Homie bridge+child tree from the specs
  and mirrors the observable model onto it (the adapter layer).
- `cta2045_proxy.core` / `cli`: wire a UCM backend to the emitter and run.

A downstream deployment customizes only the `[ebus]` / `[ucm]` config; the code
here is deployment-neutral.
"""

__version__ = "0.3.0"
