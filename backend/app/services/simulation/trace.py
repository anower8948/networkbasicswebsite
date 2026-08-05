"""The simulation trace.

The trace is the product, not a by-product. A learner runs a ping to find out
*why* it failed, so every step records what a device decided and on what
grounds — "no route to 10.0.0.5", "ARP timed out: nothing answered for
192.168.1.99", "GigabitEthernet0/1 is administratively down".

Each event also carries enough structure for the canvas to animate it: which
link, in which direction, and what kind of traffic.
"""

from __future__ import annotations

from enum import StrEnum

from app.schemas.common import APIModel


class EventKind(StrEnum):
    """What happened at one step."""

    # Layer 2
    ARP_REQUEST = "arp_request"
    ARP_REPLY = "arp_reply"
    ARP_CACHED = "arp_cached"
    SWITCH_FLOOD = "switch_flood"
    SWITCH_FORWARD = "switch_forward"
    SWITCH_LEARN = "switch_learn"

    # Layer 3 and above
    ROUTE_LOOKUP = "route_lookup"
    FORWARD = "forward"
    DELIVER = "deliver"
    REPLY = "reply"

    # Protocol milestones
    DHCP_DISCOVER = "dhcp_discover"
    DHCP_OFFER = "dhcp_offer"
    DHCP_REQUEST = "dhcp_request"
    DHCP_ACK = "dhcp_ack"
    DNS_QUERY = "dns_query"
    DNS_RESPONSE = "dns_response"
    TCP_SYN = "tcp_syn"
    TCP_SYN_ACK = "tcp_syn_ack"
    TCP_ACK = "tcp_ack"
    TCP_DATA = "tcp_data"
    TCP_FIN = "tcp_fin"
    UDP_DATAGRAM = "udp_datagram"

    # Failures
    DROP = "drop"
    TIMEOUT = "timeout"
    NOTE = "note"


class FrameSummary(APIModel):
    """Headers as they stand at this hop.

    MAC addresses are rewritten at every hop while the IP addresses stay put —
    the single most useful thing a packet trace can show a learner.
    """

    source_mac: str | None = None
    destination_mac: str | None = None
    source_ip: str | None = None
    destination_ip: str | None = None
    protocol: str | None = None
    ttl: int | None = None
    vlan: int | None = None


class TraceEvent(APIModel):
    """One step of the simulation."""

    step: int
    kind: EventKind
    device_id: str
    device_name: str
    interface: str | None = None

    # Set when the step moves traffic across a cable, so the canvas can animate.
    link_id: str | None = None
    to_device_id: str | None = None
    to_interface: str | None = None

    summary: str
    detail: str | None = None
    frame: FrameSummary | None = None
    ok: bool = True


class SimulationResult(APIModel):
    """The outcome of one simulation run."""

    success: bool
    protocol: str
    summary: str
    # Present when the run failed — the single most useful line in the trace.
    failure_reason: str | None = None
    # Plain-language suggestion, so a stuck learner has somewhere to go next.
    hint: str | None = None
    events: list[TraceEvent] = []

    @property
    def animated_steps(self) -> list[TraceEvent]:
        return [event for event in self.events if event.link_id]


class TraceBuilder:
    """Accumulates events with monotonic step numbers."""

    def __init__(self) -> None:
        self.events: list[TraceEvent] = []

    def add(
        self,
        kind: EventKind,
        device_id: str,
        device_name: str,
        summary: str,
        *,
        interface: str | None = None,
        link_id: str | None = None,
        to_device_id: str | None = None,
        to_interface: str | None = None,
        detail: str | None = None,
        frame: FrameSummary | None = None,
        ok: bool = True,
    ) -> TraceEvent:
        event = TraceEvent(
            step=len(self.events) + 1,
            kind=kind,
            device_id=device_id,
            device_name=device_name,
            interface=interface,
            link_id=link_id,
            to_device_id=to_device_id,
            to_interface=to_interface,
            summary=summary,
            detail=detail,
            frame=frame,
            ok=ok,
        )
        self.events.append(event)
        return event

    def fail(
        self,
        device_id: str,
        device_name: str,
        summary: str,
        detail: str | None = None,
        *,
        interface: str | None = None,
        kind: EventKind = EventKind.DROP,
    ) -> TraceEvent:
        return self.add(
            kind,
            device_id,
            device_name,
            summary,
            interface=interface,
            detail=detail,
            ok=False,
        )
