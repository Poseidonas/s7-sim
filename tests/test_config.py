"""Reading the plant description, and the mistakes it should refuse."""
import pytest

from s7sim import loads

GOOD = """
line: {mean_run_minutes: 5, mean_stop_minutes: 1, seed: 2}
blocks:
  10:
    tags:
      running: {offset: 0, bit: 3, type: bool, behaviour: running}
      temp:    {offset: 2, type: real, behaviour: temperature, running: 70, idle: 20}
      parts:   {offset: 6, type: dint, behaviour: counter, per_minute: 120}
      speed:   {offset: 10, type: int, behaviour: setpoint, value: 400}
"""


def test_a_block_is_sized_to_reach_its_last_tag():
    block = loads(GOOD).blocks[10]

    assert block.size == 12
    assert block.tags["running"].bit == 3


def test_the_line_is_read_in_minutes_and_kept_in_seconds():
    line = loads(GOOD).line

    assert (line.mean_run_seconds, line.mean_stop_seconds, line.seed) == (300.0, 60.0, 2)


def test_only_setpoints_are_left_to_the_client():
    plant = loads(GOOD)

    assert [t.name for t in plant.writable_tags()] == ["speed"]


def test_two_tags_may_share_a_byte_only_as_different_bits():
    plant = loads("""
blocks:
  1:
    tags:
      a: {offset: 0, bit: 0, type: bool, behaviour: running}
      b: {offset: 0, bit: 1, type: bool, behaviour: running}
""")
    assert len(plant.blocks[1].tags) == 2


def test_overlapping_tags_are_refused():
    """Both would write the same bytes every tick, and the last one would win."""
    with pytest.raises(ValueError, match="both use byte 2"):
        loads("""
blocks:
  1:
    tags:
      a: {offset: 0, type: dint, behaviour: counter}
      b: {offset: 2, type: int, behaviour: counter}
""")


def test_a_block_smaller_than_its_tags_is_refused():
    with pytest.raises(ValueError, match="declared as 4 bytes but its tags reach 8"):
        loads("""
blocks:
  1:
    size: 4
    tags:
      a: {offset: 4, type: dint, behaviour: counter}
""")


def test_a_tag_without_a_behaviour_is_refused():
    with pytest.raises(ValueError, match="does not say what it does"):
        loads("blocks:\n  1:\n    tags:\n      a: {offset: 0, type: int}\n")


def test_an_unknown_behaviour_lists_the_known_ones():
    with pytest.raises(ValueError, match="unknown behaviour 'wobble'"):
        loads("blocks:\n  1:\n    tags:\n      a: {offset: 0, type: int, behaviour: wobble}\n")


def test_an_unknown_type_lists_the_known_ones():
    with pytest.raises(ValueError, match="unknown type 'float32'"):
        loads("blocks:\n  1:\n    tags:\n      a: {offset: 0, type: float32, behaviour: counter}\n")


def test_a_bit_on_a_non_bool_is_refused():
    with pytest.raises(ValueError, match="a bit may only be given for a bool"):
        loads("blocks:\n  1:\n    tags:\n"
              "      a: {offset: 0, type: int, bit: 2, behaviour: counter}\n")


def test_an_unexpected_setting_names_the_tag_and_the_behaviour():
    with pytest.raises(ValueError, match=r"tag 'a' \(counter\)"):
        loads("blocks:\n  1:\n    tags:\n"
              "      a: {offset: 0, type: int, behaviour: counter, wobble: 3}\n")


def test_a_configuration_without_blocks_is_refused():
    with pytest.raises(ValueError, match="declares no blocks"):
        loads("line: {seed: 1}\n")


def test_a_block_without_tags_is_refused():
    with pytest.raises(ValueError, match="block 1 declares no tags"):
        loads("blocks:\n  1: {}\n")
