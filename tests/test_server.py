"""The simulator as a client sees it, over the real protocol."""
import time

import pytest
import snap7
from snap7 import util

from s7sim import Simulator, loads

PLANT = """
line: {mean_run_minutes: 0.05, mean_stop_minutes: 0.02, seed: 3}
plc: {tick_seconds: 0.1}
blocks:
  10:
    tags:
      running: {offset: 0, bit: 0, type: bool, behaviour: running}
      temp:    {offset: 2, type: real, behaviour: temperature,
                running: 74, idle: 22, tau: 5, noise: 0}
      parts:   {offset: 6, type: dint, behaviour: counter, per_minute: 600}
      speed:   {offset: 10, type: int, behaviour: setpoint, value: 1500}
"""


@pytest.fixture
def simulator(free_port):
    with Simulator(loads(PLANT), host="127.0.0.1", port=free_port) as sim:
        time.sleep(0.3)
        yield sim


@pytest.fixture
def client(simulator):
    c = snap7.client.Client()
    c.connect("127.0.0.1", 0, 1, simulator.port)
    try:
        yield c
    finally:
        c.disconnect()


def test_a_client_connects_and_reads_the_block(client):
    assert client.get_connected() is True
    assert len(client.db_read(10, 0, 12)) == 12


def test_the_values_move_on_their_own(client):
    first = util.get_dint(bytearray(client.db_read(10, 6, 4)), 0)
    time.sleep(1.2)
    second = util.get_dint(bytearray(client.db_read(10, 6, 4)), 0)

    assert second > first, "the counter did not advance"


def test_a_setpoint_survives_the_refresh(client, simulator):
    """A tag the simulator kept rewriting could not be used to test writes."""
    buffer = bytearray(2)
    util.set_int(buffer, 0, 850)
    client.db_write(10, 10, buffer)

    time.sleep(0.5)

    assert util.get_int(bytearray(client.db_read(10, 10, 2)), 0) == 850


def test_a_simulated_tag_is_put_back_after_a_write(client):
    """The opposite case, and it has to be the opposite: writing to a simulated
    tag must not stop the simulation."""
    before = util.get_real(bytearray(client.db_read(10, 2, 4)), 0)
    buffer = bytearray(4)
    util.set_real(buffer, 0, 999.0)
    client.db_write(10, 2, buffer)

    time.sleep(0.4)

    after = util.get_real(bytearray(client.db_read(10, 2, 4)), 0)
    assert after != 999.0
    assert abs(after - before) < 30


def test_the_block_a_client_reads_is_the_one_the_simulator_writes(simulator, client):
    from_client = bytes(client.db_read(10, 0, 12))
    from_server = bytes(simulator.buffer(10))

    assert from_client == from_server


def test_refreshing_to_an_explicit_time_is_reproducible(free_port):
    """The simulator is driven by a clock in service, but the state it writes
    is a function of elapsed time, so a test can ask for a moment directly."""
    plant = loads(PLANT)
    a = Simulator(plant, host="127.0.0.1", port=free_port)
    a._register()
    a.refresh(300.0)
    first = bytes(a.buffer(10))

    b = Simulator(loads(PLANT), host="127.0.0.1", port=free_port)
    b._register()
    b.refresh(300.0)

    assert bytes(b.buffer(10)) == first


def test_stopping_the_simulator_releases_the_port(free_port):
    sim = Simulator(loads(PLANT), host="127.0.0.1", port=free_port)
    sim.start()
    time.sleep(0.3)
    sim.stop()

    again = Simulator(loads(PLANT), host="127.0.0.1", port=free_port)
    again.start()
    time.sleep(0.3)
    again.stop()
