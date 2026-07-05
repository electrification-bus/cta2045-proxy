"""Native CTA-2045 UCM backend (RS485 link layer) - RESERVED.

The future "own-UCM": drive the CTA-2045 SGD<->UCM link directly over RS485
(framing, ACK/NAK, retries, sequencing) on a Pi/serial adapter, replacing the
vendor dongle entirely. This is the second UCM variant the repo is structured
for; the SkyCentrics MQTT backend is the first.

Blocked on `cta2045.link` (the RS485 link-layer implementation) landing upstream
in python-cta2045, which is itself a reserved-but-unimplemented namespace today.
Once it exists, this backend implements a `cta2045.ucm.Ucm` whose `transmit()`
writes framed bytes to the serial port and whose read loop feeds inbound bytes
to `Ucm.receive`. The `native` optional-dependency (pyserial) is already declared
in pyproject.toml.

Not yet implemented (scaffold).
"""

from __future__ import annotations


class NativeUcmBackend:
    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "native UCM backend is reserved; blocked on cta2045.link (RS485 link layer). Use ucm.kind = 'skycentrics'."
        )
