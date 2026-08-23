"""Reading the simulated plant from a YAML file.

The tag shape is deliberately the one s7-gateway uses, so a layout written here
can be pointed at by a gateway configuration without translating anything.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from snap7 import util

from .line import Line
from .tags import BEHAVIOURS, Behaviour

#: name -> (width in bytes, writer)
TYPES: dict[str, tuple[int, Any]] = {
    "bool": (1, None),  # written through set_bool, which needs the bit
    "byte": (1, util.set_byte),
    "sint": (1, util.set_sint),
    "usint": (1, util.set_usint),
    "int": (2, util.set_int),
    "uint": (2, util.set_uint),
    "word": (2, util.set_word),
    "dint": (4, util.set_dint),
    "udint": (4, util.set_udint),
    "dword": (4, util.set_dword),
    "real": (4, util.set_real),
    "lreal": (8, util.set_lreal),
}


@dataclass(frozen=True)
class Tag:
    name: str
    offset: int
    type: str
    behaviour: Behaviour
    bit: int = 0

    @property
    def size(self) -> int:
        return TYPES[self.type][0]

    @property
    def end(self) -> int:
        return self.offset + self.size

    def write(self, buffer: bytearray, line: Line, t: float) -> None:
        value = self.behaviour.value(line, t)
        if self.type == "bool":
            util.set_bool(buffer, self.offset, self.bit, bool(value))
        else:
            TYPES[self.type][1](buffer, self.offset, value)

    def address(self) -> str:
        where = f"DB?.DBX{self.offset}"
        return f"{where}.{self.bit}" if self.type == "bool" else where


@dataclass(frozen=True)
class Block:
    number: int
    size: int
    tags: dict[str, Tag]


@dataclass(frozen=True)
class Plant:
    line: Line
    blocks: dict[int, Block]
    rack: int = 0
    slot: int = 1
    port: int = 102
    tick: float = 0.5

    def writable_tags(self) -> list[Tag]:
        return [t for b in self.blocks.values() for t in b.tags.values()
                if t.behaviour.writable]


def _behaviour(tag_name: str, body: dict[str, Any]) -> Behaviour:
    kind = body.get("behaviour")
    if kind is None:
        raise ValueError(f"tag '{tag_name}' does not say what it does: add a 'behaviour'")
    if kind not in BEHAVIOURS:
        known = ", ".join(sorted(BEHAVIOURS))
        raise ValueError(f"tag '{tag_name}' has unknown behaviour '{kind}'; known are: {known}")

    cls = BEHAVIOURS[kind]
    args = {k: v for k, v in body.items() if k not in ("offset", "type", "bit", "behaviour")}
    if kind == "setpoint":
        args = {"value_": args.get("value", 0)}
    if kind == "temperature" and "running" in args:
        args["running"] = float(args["running"])
    try:
        return cls(**args)
    except TypeError as error:
        raise ValueError(f"tag '{tag_name}' ({kind}): {error}") from error


def _tag(name: str, body: dict[str, Any]) -> Tag:
    if not isinstance(body, dict):
        raise ValueError(f"tag '{name}' must be a mapping")
    for required in ("offset", "type"):
        if required not in body:
            raise ValueError(f"tag '{name}' is missing: {required}")
    kind = str(body["type"]).lower()
    if kind not in TYPES:
        known = ", ".join(sorted(TYPES))
        raise ValueError(f"tag '{name}' has unknown type '{body['type']}'; known are: {known}")
    bit = int(body.get("bit", 0))
    if kind != "bool" and "bit" in body:
        raise ValueError(f"tag '{name}': a bit may only be given for a bool")
    if not 0 <= bit <= 7:
        raise ValueError(f"tag '{name}': bit must be between 0 and 7")
    if int(body["offset"]) < 0:
        raise ValueError(f"tag '{name}': offset must not be negative")
    return Tag(name=name, offset=int(body["offset"]), type=kind,
               bit=bit, behaviour=_behaviour(name, body))


def _block(number: Any, body: dict[str, Any]) -> Block:
    try:
        number = int(number)
    except (TypeError, ValueError):
        raise ValueError(f"block '{number}' is not a number") from None
    tags_raw = (body or {}).get("tags")
    if not tags_raw:
        raise ValueError(f"block {number} declares no tags")
    tags = {name: _tag(name, tag_body) for name, tag_body in tags_raw.items()}

    _reject_overlaps(number, tags)
    needed = max(t.end for t in tags.values())
    size = int(body.get("size", needed))
    if size < needed:
        raise ValueError(
            f"block {number} is declared as {size} bytes but its tags reach {needed}")
    return Block(number=number, size=size, tags=tags)


def _reject_overlaps(number: int, tags: dict[str, Tag]) -> None:
    """Two tags sharing bytes would each overwrite the other every tick."""
    claimed: dict[int, tuple[str, int | None]] = {}
    for tag in sorted(tags.values(), key=lambda t: (t.offset, t.bit)):
        for byte in range(tag.offset, tag.end):
            bit = tag.bit if tag.type == "bool" else None
            owner = claimed.get(byte)
            if owner is None:
                claimed[byte] = (tag.name, bit)
                continue
            other_name, other_bit = owner
            if bit is not None and other_bit is not None and bit != other_bit:
                continue  # different bits of the same byte are fine
            raise ValueError(
                f"block {number}: tags '{other_name}' and '{tag.name}' both use byte {byte}")


def loads(text: str) -> Plant:
    try:
        raw = yaml.safe_load(text) or {}
    except yaml.YAMLError as error:
        raise ValueError(f"the plant description is not valid YAML: {error}") from error
    if not isinstance(raw, dict):
        raise ValueError("the configuration must be a mapping at the top level")

    blocks_raw = raw.get("blocks")
    if not blocks_raw:
        raise ValueError("the configuration declares no blocks")

    line_raw = raw.get("line") or {}
    line = Line(
        mean_run_seconds=float(line_raw.get("mean_run_minutes", 12)) * 60,
        mean_stop_seconds=float(line_raw.get("mean_stop_minutes", 3)) * 60,
        seed=int(line_raw.get("seed", 1)),
    )
    plc = raw.get("plc") or {}
    return Plant(
        line=line,
        blocks={b.number: b for b in (_block(n, body) for n, body in blocks_raw.items())},
        rack=int(plc.get("rack", 0)),
        slot=int(plc.get("slot", 1)),
        port=int(plc.get("port", 102)),
        tick=float(plc.get("tick_seconds", 0.5)),
    )


def load(path: str | Path) -> Plant:
    try:
        return loads(Path(path).read_text(encoding="utf-8"))
    except ValueError as error:
        raise ValueError(f"{path}: {error}") from error
