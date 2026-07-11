"""cta2045-proxy entry point."""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading

from .config import load
from .core import Cta2045Proxy


def _version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("cta2045-proxy")
    except PackageNotFoundError:  # running from a source tree without an install
        return "0+unknown"


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="cta2045-proxy")
    ap.add_argument("--config", required=True, help="path to a TOML config (see config/config.example.toml)")
    ap.add_argument(
        "--log-level",
        default=os.getenv("LOG_LEVEL", "INFO"),
        help="logging level (default: INFO, or $LOG_LEVEL)",
    )
    ap.add_argument("--version", action="version", version=f"%(prog)s {_version()}")
    args = ap.parse_args(argv)

    log_level = getattr(logging, args.log_level.upper(), logging.INFO)
    logging.basicConfig()
    log = logging.getLogger("cta2045_proxy")
    log.setLevel(log_level)

    cfg = load(args.config)
    proxy = Cta2045Proxy(cfg, log=log)
    proxy.start()
    log.info("reason=cta2045ProxyReady")

    shutdown = threading.Event()

    def _handle(signum, _frame):
        log.info(f"reason=signalReceived,signal={signum}")
        shutdown.set()

    signal.signal(signal.SIGTERM, _handle)
    signal.signal(signal.SIGINT, _handle)
    shutdown.wait()

    log.info("reason=cta2045ProxyShutdown")
    proxy.stop()
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:  # noqa: BLE001 - top-level guard
        logging.exception(e)
        sys.exit(1)
