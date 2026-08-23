# s7-sim

A Siemens S7 line you can run in a container.

It answers the S7 protocol like a controller does, and the values it serves
move the way a line moves: counters advance while it runs and freeze when it
stops, a temperature climbs and falls back, and the whole thing stops at random
intervals and starts again.

```console
$ docker run -p 10102:1102 ghcr.io/poseidonas/s7-sim
```

Point anything that speaks S7 at it — `python-snap7`, a gateway, your own code —
and develop against a plant that behaves like one, without hardware, a licence
or a Siemens account.

## The whole stack, in one command

```console
git clone https://github.com/Poseidonas/s7-sim && cd s7-sim
docker compose up
```

That brings up four things wired together: the simulated line, an
[s7-gateway](https://github.com/Poseidonas/s7-gateway) reading it over S7,
Prometheus scraping the gateway, and Grafana with a dashboard already loaded.

| | |
| --- | --- |
| http://localhost:3000 | Grafana, no login. Line state, filler temperature, bottles per minute, current stop |
| http://localhost:8088/docs | the gateway's API |
| http://localhost:9090 | Prometheus |
| `localhost:10102` | the line itself, over S7 |

Everything is provisioned, so the dashboard has data in it the moment it opens.

## What it is not

**It is not a PLC.** It speaks the protocol and serves plausible values; it runs
no user program, has no cycle, no I/O, no diagnostics buffer and no safety.

Where it is known to differ from a controller, and this matters if you are using
it to test error handling:

- **A read from a data block that does not exist returns fabricated bytes**
  instead of an error. This is `snap7.server` underneath, reported upstream at
  [python-snap7#578](https://github.com/gijzelaerr/python-snap7/discussions/578).
  A real CPU answers with an address error. If you are testing what your code
  does with a wrong address, this is the one thing you cannot test here.
- **A read past the end of a block is padded with zeros** rather than refused.
- **A normal client disconnect is logged as an error** by the server.
- There is no PUT/GET permission and no optimized block access, so neither of
  the two settings that gate a real S7-1200 or S7-1500 applies. Code that works
  here can still be refused by a real CPU for that reason alone.

Use it to build and to demonstrate. Confirm against hardware before you trust it.

## Describing a plant

Everything is one YAML file. Each tag names its own address, exactly as a
standard-access data block lays them out, and says what it does.

```yaml
line:
  mean_run_minutes: 12     # average time between stops
  mean_stop_minutes: 3     # average length of a stop
  seed: 1                  # the same seed gives the same day, every time

blocks:
  10:
    tags:
      running:
        offset: 0
        bit: 0
        type: bool
        behaviour: running

      filler_temp:
        offset: 6
        type: real
        behaviour: temperature
        running: 74.0        # settles here while producing
        idle: 21.5           # and falls back to here when stopped
        tau: 180             # seconds to cover 63% of the gap
        noise: 0.3

      bottles_filled:
        offset: 10
        type: dint
        behaviour: counter
        per_minute: 420

      line_speed:
        offset: 18
        type: int
        behaviour: setpoint  # written once, then left to the client
        value: 420
```

Check it before starting anything. This reads the file only:

```console
$ s7-sim --config examples/line.yml --check
line: runs 12 min on average, stops for 3 min, seed 1
DB10  24 bytes
    running              bool   DB10.DBX0.0        r-  running
    stopped_for          real   DB10.DBX2          r-  stoppedfor
    filler_temp          real   DB10.DBX6          r-  temperature
    bottles_filled       dint   DB10.DBX10         r-  counter
    bottles_rejected     dint   DB10.DBX14         r-  counter
    line_speed           int    DB10.DBX18         rw  setpoint
    target_temp          real   DB10.DBX20         rw  setpoint
```

### Behaviours

| | |
| --- | --- |
| `running` | true while the line produces |
| `counter` | advances at `per_minute` **only while running**, so a stop shows as a flat line. `fraction` counts a share of the same production, which is how a reject counter is written |
| `temperature` | approaches `running` while producing and `idle` while stopped, as a first-order lag with time constant `tau`, plus optional `noise` |
| `stopped_for` | seconds the current stop has lasted, zero while running |
| `setpoint` | written once at startup and never again, so a client can write it and have it stay written |

Types: `bool` `byte` `sint` `usint` `int` `uint` `word` `dint` `udint` `dword`
`real` `lreal`.

Two tags may share a byte only as different bits. Anything else that overlaps is
refused when the file is read, because both would write the same bytes every
tick and the last one would win.

## Reproducibility

The line is a function of elapsed time rather than a loop that mutates state.
The same seed produces the same stops, at the same seconds, on every run and on
every machine. That is what makes it useful for a test rather than only a demo:
a stop you cannot reproduce cannot be asserted on.

```python
from s7sim import Simulator, loads

sim = Simulator(loads(open("line.yml").read()))
sim._register()
sim.refresh(1800.0)          # the plant half an hour in
print(sim.buffer(10).hex())  # always the same bytes
```

## Running it without Docker

```console
pip install s7-sim
s7-sim --config examples/line.yml --port 1102
```

Python 3.11+. `python-snap7` 3.1+ speaks S7 in Python over a plain socket, so
there is nothing to compile.

### About port 102

S7 clients expect port 102, which is privileged. The container runs as a
non-root user and listens on 1102, so publish it where you need it:

```console
docker run -p 102:1102 ghcr.io/poseidonas/s7-sim     # the real port, needs a privileged bind
docker run -p 10102:1102 ghcr.io/poseidonas/s7-sim   # anywhere else
```

## Development

```console
pip install -e ".[test]"
pytest
```

The tests drive a real `snap7` client against the simulator over the actual
protocol. Nothing about snap7 is mocked.

## Licence

MIT
