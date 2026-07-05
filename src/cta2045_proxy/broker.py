"""Broker-config resolution: the deployment-customization seam.

`[ebus]` (Homie output) and `[ucm.skycentrics]` (UCM transport) each describe an
MQTT connection. This turns a TOML section into the dict that
`ebus_mqtt_client.MqttClient.from_config` expects, expanding `${ENV}` references
(so secrets stay out of the config file). A downstream deployment customizes
ONLY these sections / env vars, never the proxy code.
"""

from __future__ import annotations

import os
import re

_ENV_RE = re.compile(r"\$\{([A-Z0-9_]+)\}")


def _expand(value):
    """Expand ${ENV} inside a string value; pass non-strings through."""
    if not isinstance(value, str):
        return value
    return _ENV_RE.sub(lambda m: os.getenv(m.group(1), ""), value)


def resolve_broker_cfg(section: dict, *, password_env: str = "EBUS_MQTT_PASS") -> dict:
    """Build an MqttClient.from_config-shaped dict from a TOML broker section.

    TODO(repo-local): confirm the exact key shape against
    ebus_mqtt_client.MqttClient.from_config (host/port/authentication{type,
    username,password}). A downstream deployment feeds broker host/credentials in
    via env/config rather than hardcoding them here.
    """
    host = _expand(section.get("host", "localhost"))
    port = int(section.get("port", 1883))
    username = _expand(section.get("username")) if section.get("username") else None
    password = os.getenv(password_env) or None

    cfg: dict = {"host": host, "port": port}
    if username:
        cfg["authentication"] = {
            "type": "USER_PASS",
            "username": username,
            "password": password,
        }
    return cfg
