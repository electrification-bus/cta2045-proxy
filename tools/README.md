# tools — configure & inspect a SkyCentrics Ethernet UCM

Helper scripts for bringing up a SkyCentrics Ethernet UCM (US08C) and pointing it at a broker so `cta2045-proxy` can bridge it onto eBus. Bash + `curl` + `mosquitto-clients`; they run on macOS (bash 3.2) and Linux, from anywhere on the LAN that can reach the UCM.

| Script | Purpose |
|---|---|
| [`ucm-discover`](ucm-discover) | Find SkyCentrics UCM(s) on the LAN by MAC OUI (`arp -a`, optional `--sweep`). |
| [`ucm-configure`](ucm-configure) | Point a UCM at a broker via its built-in web UI (MQTT + optional static IP, then reboot). |
| [`ucm-watch`](ucm-watch) | Tail a UCM's live `devices/<MAC>/#` MQTT traffic to confirm it is connected. |

Each takes `--help`.

## End-to-end bring-up

```bash
# 1. Find the UCM on your LAN (prime the ARP cache first if it's not listed).
./ucm-discover --sweep
#   192.168.1.53     84FEDC538C72   SkyCentrics Ethernet UCM (US08C-series, OUI 84:FE:DC)

# 2. Point it at your broker (HTTP Basic auth to the UCM is admin / the UCM's MAC).
#    NOTE: the EUCM will not connect unless BOTH --mqtt-user and --mqtt-pass are
#    set, even on an anonymous broker (any non-empty pair works there).
./ucm-configure --ucm-ip 192.168.1.53 --ucm-mac 84FEDC538C72 \
                --broker-host <broker-host-or-ip> --broker-port 1883 \
                --mqtt-user ebus --mqtt-pass ebusdemo
#   ...saves MQTT settings, then reboots the UCM (~45s to come back).

# 3. Confirm it reconnected and is publishing.
./ucm-watch --mac 84FEDC538C72 --broker-host <broker-host-or-ip>
#   <ts>  devices/84FEDC538C72/data     {"t":..., "d":"..."}
#   <ts>  devices/84FEDC538C72/devinfo  {"SGD":{"d":"..."}}

# 4. Run the proxy; watch translated eBus/Homie devices appear under ebus/5/#.
cta2045-proxy --config ../config/config.toml
mosquitto_sub -h <broker-host> -t 'ebus/5/#' -v
```

The UCM speaks **plaintext** MQTT and must be able to **publish**, so the broker needs an anonymous (or credentialed) read/write listener on the configured port.

## A local broker for testing

Any Mosquitto reachable from both the UCM and the proxy works. Two easy options:

**Sibling `broker-quickstart` (the eBus way).** [`broker-quickstart`](https://github.com/electrification-bus/broker-quickstart) stands up an eBus Mosquitto bundle. Its default `discovery` profile makes the plaintext `1883` listener anonymous **read-only**, which blocks a UCM's publishes — so switch to the **`open`** profile (anonymous read/write plaintext) for UCM bring-up. On a Mac:

```bash
brew install mosquitto
cd /path/to/broker-quickstart
python3 -m venv .venv && source .venv/bin/activate && pip install -e '.[laptop]'
# start in the open profile (anon read+write on 1883); see its docs/security-profiles.md
python -m laptop.run --profile open
```

Point the UCM at your Mac's `<name>.local` (or LAN IP) on port `1883`.

> **Do not expose an `open`-mode broker to an untrusted network.** It is for local bring-up only. For anything beyond your bench, use the `discovery`/`strict` mTLS profiles and give the proxy a client certificate.

**Bare Mosquitto (minimal fallback).** If you just want a throwaway broker:

```bash
brew install mosquitto        # or: apt-get install mosquitto mosquitto-clients
printf 'listener 1883 0.0.0.0\nallow_anonymous true\n' > /tmp/mosq-open.conf
mosquitto -c /tmp/mosq-open.conf -v
```

Point both the UCM (`ucm-configure --broker-host <this-machine>`) and the proxy (`[ebus] host`) at this machine's LAN IP.
