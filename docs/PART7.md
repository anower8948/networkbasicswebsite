# Part 7 — Packet Simulation Engine

Parts 4–6 built a network you could draw, configure and log into. Part 7 makes
it *carry traffic*: ARP, ICMP, DHCP, DNS, TCP and UDP run over the topology,
and every decision a device makes is recorded as a step you can read.

## The thesis: the trace is the product

A simulator that only answers "ping worked" or "ping failed" teaches nothing.
The value is in the middle — the moment a host compares a destination to its
own subnet mask and decides to hand the frame to the gateway instead. So the
engine's output is not a boolean, it is a list of `TraceEvent`s, each one saying
which device acted, on which interface, what it decided, and on what grounds.

A routed ping across two subnets produces 24 steps:

```
 1  PC1                          Pinging 10.0.0.10 with 4 echo requests
 2  PC1                          10.0.0.10 is not local — sending to the gateway 192.168.1.1
 3  PC1 · Ethernet0              ARP: who has 192.168.1.1?
 4  R1 · GigabitEthernet0/0      ARP reply: 192.168.1.1 is at 02:08:60:33:DE:80
 5  PC1 · Ethernet0              ICMP echo request out Ethernet0 toward 192.168.1.1
 6  SW1 · FastEthernet0/1        Switching frame toward 02:08:60:33:DE:80
 7  R1 · GigabitEthernet0/1      10.0.0.10 is on the local subnet 10.0.0.0/24
 8  R1 · GigabitEthernet0/1      ARP: who has 10.0.0.10?
 9  SRV1 · Ethernet0             ARP reply: 10.0.0.10 is at 02:8C:CD:56:CF:36
10  R1 · GigabitEthernet0/1      ICMP echo request out GigabitEthernet0/1 toward 10.0.0.10
11  SW2 · GigabitEthernet0/1     Switching frame toward 02:8C:CD:56:CF:36
12  SRV1                         ICMP echo request delivered to 10.0.0.10
13  SRV1                         Echo reply to 192.168.1.10
    … the return leg, simulated separately …
24  PC1                          ICMP echo reply delivered to 192.168.1.10
```

Steps 2 and 7 are the lesson. Steps 3–4 versus 8–9 are the other lesson: ARP
happens **once per segment**, not once per ping. And expanding any forwarding
step shows the frame headers, which is the clearest way to demonstrate that
**MAC addresses are rewritten at every hop while the IP addresses never
change**.

## Failure diagnosis is a first-class feature

Every classic misconfiguration produces a message naming the *actual* cause,
not a generic timeout. This is the part of the engine with the most code in it,
and deliberately so — a learner who breaks their network needs to be told what
they broke.

| What is wrong | What the simulator says |
|---|---|
| No default gateway | "PC1 has no default gateway, so it cannot reach another network." |
| Gateway address nobody owns | "No device in this network is configured with 192.168.1.254." |
| Destination interface shut | "SRV1 has 10.0.0.10 on Ethernet0, but that interface is administratively down." |
| Wrong cable type | "The link between SW1 and R1 uses a crossover cable, which is the wrong type — no signal passes, so R1 is unreachable." |
| Cable disabled | "The link between SW1 and R1 is disabled, so the segment is cut before it reaches R1." |
| Ports in different VLANs | "SRV1 holds 10.0.0.10 but is not reachable in this broadcast domain — check that both ports are in the same VLAN." |
| Route exists but the exit is shut | Names the shut interface rather than blaming the routing table. |
| Reply cannot get back | "Request reached the destination, but the reply could not get back." |

Two of these needed real work to get right, and both were bugs found during
verification rather than designed in:

* **A shut interface was being reported as a missing route.** `_no_route_detail`
  now checks whether an interface *would* have matched had it been up, and says
  so. "No route to 10.0.0.10" sends someone to the routing table; "the interface
  that reaches it is shut" sends them to `no shutdown`.
* **A wrong cable was being reported as a VLAN mismatch.** `blocked_links_near`
  walks the segment looking for a link that is down or miscabled *before*
  falling back to the VLAN explanation, and names the two devices at its ends.

The return leg is simulated as a separate packet for the same reason: a one-way
path is a real failure mode, and someone who has configured routing outbound
only must see the reply fail rather than get a false success.

## Architecture

Four modules under `app/services/simulation/`, layered so each has one job:

```
  network.py     topology + configs  →  MACs, broadcast domains, routing tables
       ↓
  forwarding.py  ARP, egress selection, hop-by-hop delivery, failure diagnosis
       ↓
  protocols.py   ICMP · ARP · DHCP · DNS · TCP · UDP flows
       ↓
  trace.py       the event vocabulary everything above writes into
```

`trace.py` sits at the bottom as a pure data module with no dependencies, so
the layers above cannot become circular.

### network.py — resolving the topology

Turns the editable representation into something forwarding can run over.

**MAC addresses are derived, not allocated:** `sha256(device_id:interface)`
truncated to five octets behind a `02:` locally-administered prefix. A learner
comparing two runs sees the same addresses both times; random MACs would make
traces impossible to follow.

**Broadcast domains** are computed by flooding across switches. There are two
entry points, and the distinction matters:

* `broadcast_domain(device, interface, vlan)` — flood *out of* a port.
* `flood_into(device, ingress, vlan)` — flood *from a frame that just arrived*.
  The VLAN is taken from the access port the frame landed on, because a host
  has no VLAN concept: the switch port decides.

Getting this wrong the first time made VLAN separation untestable, because the
sender was assuming a VLAN it has no way to know.

**Routing tables** combine connected, static and dynamic routes, sorted by
longest prefix then administrative distance. Dynamic routing (OSPF, EIGRP, RIP)
is resolved by flooding advertised networks between routers that share a
protocol and a working link. Convergence, metrics and DR/BDR election are out of
scope for a teaching simulator — reachability is what the lesson needs, and the
simplification is documented at the top of the module.

### forwarding.py — the hop-by-hop walk

Two rules drive everything, and both are traced explicitly because both are the
concepts being taught:

1. **A host compares the destination to its own subnet.** Same subnet → ARP for
   the destination. Different subnet → ARP for the gateway.
2. **MAC addresses are rewritten at every hop; IP addresses are not.**

An ARP cache means a second packet does not re-ARP. TTL starts at 64 and a
`MAX_HOPS = 16` ceiling guarantees a packet bouncing between two misconfigured
routers terminates rather than hanging the request.

### protocols.py — the exchanges

* **ICMP** — echo request plus a separately simulated reply; traceroute by
  letting the TTL expire at each hop.
* **ARP** — resolution on its own, for teaching Layer 2 without Layer 3.
* **DHCP** — the full DORA exchange against a router pool or a server, honouring
  excluded ranges. On failure the trace mentions the 169.254 APIPA address the
  client would end up with, because that is what a learner will actually see.
* **DNS** — a query to the configured resolver; NXDOMAIN when no device answers.
* **TCP** — three-way handshake, data, and an orderly four-way close.
* **UDP** — one datagram, no handshake, no reply.

Modelling TCP and UDP separately is the point: the *difference* is the lesson.
TCP costs three round trips before a byte of data moves; UDP costs none, and
its hint says so — loss is silent.

## The API

One stateless endpoint:

```
POST /api/v1/simulation/run
{ document, sourceDeviceId, protocol, destination, port, count }
→ { success, protocol, summary, failureReason, hint, events[] }
```

Stateless like the rest of the simulator: the client posts the topology it is
*currently editing*, not a saved one. A learner can change a mask, re-run, and
see the difference without their scratch work becoming a saved topology.

Device configs travel inside the document as free-form JSON, so a config the
simulator cannot parse — from an older export, or a hand-edited import — now
returns **422 naming the device** rather than a 500. This was found in browser
verification, not by the tests.

`ping` at the Cisco CLI runs the same engine, printing `!!!!!` or `.....` with
IOS success rates and a `%` line diagnosing the failure.

## The UI

The simulator page's side panel gained a **Simulate** tab beside Inspect:
protocol picker, destination, and the trace.

**Playback makes the trace teachable.** `usePacketAnimation` steps through the
events at 900 ms each with play, pause, step forward, step back, restart, and
click-to-seek on any step. The packet itself is an SVG circle riding the edge's
own path via `animateMotion`, so it follows every bend the cable takes instead
of cutting across the canvas — and it runs backwards (`keyPoints="1;0"`) when
the trace says the frame came from the link's target end.

Steps are colour-coded by meaning so the trace scans at a glance, the current
step auto-expands its detail line, and clicking a step reveals the frame
headers at that hop.

## Verification

Backend: **307 tests**, `ruff` clean, `mypy` clean across 78 files, `alembic
check` reports no drift. Frontend: **87 tests**, `tsc` clean, `eslint` clean,
`vite build` succeeds.

36 of the backend tests are the simulator's, and they are written as
*assertions about what it teaches* rather than about its internals: that the
trace shows the gateway decision, that ARP happens per segment, that MACs are
rewritten while IPs are not, that each classic mistake names its true cause.

Verified end to end in a browser against a five-device routed lab
(PC1—SW1—R1—SW2—SRV1 across 192.168.1.0/24 and 10.0.0.0/24):

* a ping from PC1 to 10.0.0.10 renders all 24 steps, animates the packet along
  each link in turn, and reports `4/4 received, 3 hops`
* pointing PC1 at a gateway nobody owns produces the red failure card with
  *"No device in this network is configured with 192.168.1.254"*
* DHCP from PC1 leases 192.168.1.21 from R1 — the first address after the
  configured exclusion — with the gateway and DNS server attached

## Bugs found and fixed during this part

* **Switch ports defaulted to down**, so every ARP failed. Real switch ports are
  up out of the box; router interfaces are not. Fixed as a *class* of problem
  with a tri-state `enabled: bool | None` and a shared `admin_up(interface,
  kind)` helper, rather than special-casing the simulator — the forms, the CLI,
  `show ip interface brief` and the warnings now all agree.
* **A circular import** (`schemas.topology` → `device_catalog` →
  `services/__init__` → `topology_service` → back to a half-built
  `schemas.topology`). Fixed by emptying the package-root re-exports in
  `services/`, `repositories/` and `schemas/` after confirming nothing imported
  from them — a package root that re-exports everything couples every module in
  it to every other.
* **`setState` during render.** `DeviceConfigWindow` called the parent's
  `onChange` from inside a `setConfig` functional updater, and React may run
  updaters during render — so editing a field wrote to the simulator page
  mid-render. Patches only ever come from event handlers, so the next config is
  now derived outside the updater.
* **A 500 on unparseable device config**, described above.

## What Part 8 builds on this

The engine already exposes what labs need: `SimulationResult.success` is a
gradeable assertion, `TraceEvent` is the evidence, and a disabled link is drawn
faint on the canvas — which is how troubleshooting mode will inject faults.
