"""Serving the simulated plant over the S7 protocol.

Each block is a bytearray registered with the snap7 server. The server keeps a
reference to it rather than a copy, so refreshing the plant is a matter of
writing into the same buffer the clients are reading from.
"""
from __future__ import annotations

import logging
import threading
import time

import snap7
from snap7.server import Server

from .config import Plant

logger = logging.getLogger(__name__)


class Simulator:
    """A running S7 server whose data blocks follow the line."""

    def __init__(self, plant: Plant, host: str = "0.0.0.0", port: int | None = None) -> None:
        self._plant = plant
        self._host = host
        self._port = port if port is not None else plant.port
        self._server = Server()
        self._buffers: dict[int, bytearray] = {}
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._started_at = 0.0

    @property
    def port(self) -> int:
        return self._port

    def elapsed(self) -> float:
        return time.monotonic() - self._started_at

    def _register(self) -> None:
        for block in self._plant.blocks.values():
            buffer = bytearray(block.size)
            # Writable tags are placed once. The refresh leaves them alone so a
            # client can write one and have it stay written.
            for tag in block.tags.values():
                if tag.behaviour.writable:
                    tag.write(buffer, self._plant.line, 0.0)
            self._buffers[block.number] = buffer
            self._server.register_area(snap7.type.SrvArea.DB, block.number, buffer)
            logger.info("DB%d registered, %d bytes, %d tags",
                        block.number, block.size, len(block.tags))

    def refresh(self, t: float) -> None:
        """Bring every simulated tag up to elapsed time ``t``."""
        for block in self._plant.blocks.values():
            buffer = self._buffers[block.number]
            for tag in block.tags.values():
                if not tag.behaviour.writable:
                    tag.write(buffer, self._plant.line, t)

    def _run(self) -> None:
        while not self._stop.is_set():
            self.refresh(self.elapsed())
            self._stop.wait(self._plant.tick)

    def start(self) -> None:
        self._register()
        self._started_at = time.monotonic()
        self.refresh(0.0)
        self._server.start_to(self._host, self._port)
        logger.info("listening on %s:%d, rack %d slot %d",
                    self._host, self._port, self._plant.rack, self._plant.slot)
        self._thread = threading.Thread(target=self._run, name="s7sim", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        try:
            self._server.stop()
            self._server.destroy()
        except Exception:  # noqa: BLE001 - shutdown must not raise
            logger.debug("server already down", exc_info=True)

    def __enter__(self) -> Simulator:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()

    def buffer(self, block: int) -> bytearray:
        """The live bytes of one block. Used by the tests."""
        return self._buffers[block]
