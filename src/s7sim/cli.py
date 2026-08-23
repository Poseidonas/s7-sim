"""Starting the simulator from a terminal or a container."""
from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading

from . import __version__
from . import config as config_module
from .server import Simulator


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="s7-sim",
        description="Serve a simulated Siemens S7 line over the S7 protocol.")
    parser.add_argument("-c", "--config", required=True,
                        help="path to the plant description")
    parser.add_argument("--host", default="0.0.0.0",
                        help="address to listen on (default: %(default)s)")
    parser.add_argument("--port", type=int,
                        help="port to listen on (default: the one in the file, or 102)")
    parser.add_argument("--log-level", default="info",
                        choices=["debug", "info", "warning", "error"])
    parser.add_argument("--check", action="store_true",
                        help="read the plant, print its layout and exit")
    parser.add_argument("--health", action="store_true",
                        help="connect as an S7 client and exit 0 if the CPU answers")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser.parse_args(argv)


def _print_layout(plant) -> None:
    line = plant.line
    print(f"line: runs {line.mean_run_seconds / 60:g} min on average, "
          f"stops for {line.mean_stop_seconds / 60:g} min, seed {line.seed}")
    for block in sorted(plant.blocks.values(), key=lambda b: b.number):
        print(f"DB{block.number}  {block.size} bytes")
        for tag in sorted(block.tags.values(), key=lambda t: (t.offset, t.bit)):
            where = f"DB{block.number}.DBX{tag.offset}"
            if tag.type == "bool":
                where += f".{tag.bit}"
            access = "rw" if tag.behaviour.writable else "r-"
            print(f"    {tag.name:20} {tag.type:6} {where:18} {access}  "
                  f"{type(tag.behaviour).__name__.lower()}")


def _health(plant, port: int | None) -> int:
    """Speak the protocol rather than opening a bare socket.

    A TCP connection with no S7 handshake is logged by the server as a failed
    ISO connection, so a bare socket check makes a healthy container look like
    it is being probed by something broken.
    """
    import snap7

    block = min(plant.blocks)
    client = snap7.client.Client()
    try:
        client.connect("127.0.0.1", plant.rack, plant.slot, port or plant.port)
        # Read a real block rather than asking for the CPU state: the state
        # request makes the server parse an address it was not given, which it
        # resolves to a block that does not exist and logs as a failure.
        client.db_read(block, 0, 1)
    except Exception as error:  # noqa: BLE001 - any failure means unhealthy
        print(f"s7-sim: {error}", file=sys.stderr)
        return 1
    finally:
        try:
            client.disconnect()
        except Exception:  # noqa: BLE001
            pass
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=args.log_level.upper(),
                        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s")
    try:
        plant = config_module.load(args.config)
    except (OSError, ValueError) as error:
        print(f"s7-sim: {error}", file=sys.stderr)
        return 2

    if args.check:
        _print_layout(plant)
        return 0

    if args.health:
        return _health(plant, args.port)

    simulator = Simulator(plant, host=args.host, port=args.port)
    stop = threading.Event()

    def shutdown(*_: object) -> None:
        stop.set()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    simulator.start()
    try:
        stop.wait()
    finally:
        simulator.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
