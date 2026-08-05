"""Frame and packet forwarding.

The core of the simulator: getting one packet from a source device to a
destination, recording every decision on the way, and stopping with a specific
reason when it cannot.

Two rules drive everything:

* **A host compares the destination to its own subnet.** Same subnet → ARP for
  the destination itself. Different subnet → ARP for the gateway. Getting this
  wrong is the classic beginner error, and the trace names it explicitly.
* **MAC addresses are rewritten at every hop; IP addresses are not.** Each
  `FrameSummary` shows both, which is the clearest way to teach the difference.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass

from app.services.simulation.network import Network, SimDevice, SimInterface
from app.services.simulation.trace import (
    EventKind,
    FrameSummary,
    TraceBuilder,
)

DEFAULT_TTL = 64
# A packet bouncing between two misconfigured routers must terminate.
MAX_HOPS = 16


@dataclass(slots=True)
class DeliveryOutcome:
    """Whether a packet arrived, and why not if it did not."""

    delivered: bool
    reason: str | None = None
    hint: str | None = None
    hops: int = 0
    final_device: str | None = None


class Forwarder:
    """Walks a packet through the network, tracing every decision."""

    def __init__(self, network: Network, trace: TraceBuilder) -> None:
        self.network = network
        self.trace = trace
        # Populated as ARP resolves, so a second packet does not re-ARP.
        self.arp_cache: dict[tuple[str, str], str] = {}

    # ------------------------------------------------------------------ #
    # ARP
    # ------------------------------------------------------------------ #
    def resolve_arp(self, device: SimDevice, egress: SimInterface, target_ip: str) -> str | None:
        """Find the MAC for `target_ip` on the segment behind `egress`.

        Returns None when nothing answers, which is what a real ARP timeout
        looks like and is one of the most common reasons a ping fails.
        """
        cached = self.arp_cache.get((device.id, target_ip))
        if cached:
            self.trace.add(
                EventKind.ARP_CACHED,
                device.id,
                device.name,
                f"{target_ip} is already in the ARP cache",
                interface=egress.name,
                detail=f"{target_ip} is at {cached}",
            )
            return cached

        # A host has no VLAN concept; the switch port it reaches decides.
        vlan = egress.access_vlan if egress.switchport_mode else None
        self.trace.add(
            EventKind.ARP_REQUEST,
            device.id,
            device.name,
            f"ARP: who has {target_ip}?",
            interface=egress.name,
            link_id=self._link_id(device.id, egress.name),
            detail=f"Broadcast from {egress.ip or 'unassigned'} on {egress.name}",
            frame=FrameSummary(
                source_mac=egress.mac,
                destination_mac="FF:FF:FF:FF:FF:FF",
                source_ip=egress.ip,
                destination_ip=target_ip,
                protocol="ARP",
                vlan=vlan if egress.switchport_mode else None,
            ),
        )

        # The request floods the broadcast domain; whoever holds the address
        # answers.
        for peer_device_id, peer_interface_name in self.network.broadcast_domain(
            device.id, egress.name, vlan
        ):
            peer = self.network.devices.get(peer_device_id)
            if peer is None:
                continue
            peer_interface = peer.interfaces.get(peer_interface_name)
            if peer_interface is None or not peer_interface.enabled:
                continue
            if peer_interface.ip != target_ip:
                continue

            self.arp_cache[(device.id, target_ip)] = peer_interface.mac
            self.trace.add(
                EventKind.ARP_REPLY,
                peer.id,
                peer.name,
                f"ARP reply: {target_ip} is at {peer_interface.mac}",
                interface=peer_interface.name,
                link_id=self._link_id(peer.id, peer_interface.name),
                to_device_id=device.id,
                frame=FrameSummary(
                    source_mac=peer_interface.mac,
                    destination_mac=egress.mac,
                    source_ip=target_ip,
                    destination_ip=egress.ip,
                    protocol="ARP",
                ),
            )
            return peer_interface.mac

        self.trace.fail(
            device.id,
            device.name,
            f"ARP timed out for {target_ip}",
            self._arp_failure_detail(device, egress, target_ip),
            interface=egress.name,
            kind=EventKind.TIMEOUT,
        )
        return None

    def _arp_failure_detail(self, device: SimDevice, egress: SimInterface, target_ip: str) -> str:
        """Explain why nothing answered — the useful half of the message."""
        link = self.network.link_on(device.id, egress.name)
        if link is None:
            return f"{egress.name} has no cable attached."
        if not link.enabled:
            return f"The cable on {egress.name} is disabled."
        if not link.cable_ok:
            return (
                f"The cable on {egress.name} is the wrong type "
                f"({link.cable.value.replace('_', ' ')}), so no signal passes."
            )

        holder = self.network.device_owning(target_ip)
        if holder is None:
            return f"No device in this network is configured with {target_ip}."

        holder_interface = holder.interface_holding(target_ip)
        if holder_interface and not holder_interface.enabled:
            return (
                f"{holder.name} has {target_ip} on {holder_interface.name}, "
                "but that interface is administratively down."
            )

        for blocked in self.network.blocked_links_near(device.id, egress.name):
            a = self.network.devices[blocked.a_device].name
            b = self.network.devices[blocked.b_device].name
            if not blocked.enabled:
                return (
                    f"The link between {a} and {b} is disabled, so the segment is "
                    f"cut before it reaches {holder.name}."
                )
            return (
                f"The link between {a} and {b} uses a "
                f"{blocked.cable.value.replace('_', ' ')} cable, which is the wrong "
                f"type — no signal passes, so {holder.name} is unreachable."
            )

        return (
            f"{holder.name} holds {target_ip} but is not reachable in this "
            "broadcast domain — check that both ports are in the same VLAN."
        )

    def _link_id(self, device_id: str, interface: str) -> str | None:
        link = self.network.link_on(device_id, interface)
        return link.id if link else None

    # ------------------------------------------------------------------ #
    # Egress selection
    # ------------------------------------------------------------------ #
    def choose_egress(
        self, device: SimDevice, destination: str
    ) -> tuple[SimInterface, str] | tuple[None, None]:
        """Pick the exit interface and the next-hop IP to ARP for.

        This is where "same subnet or not" is decided, and the trace says which
        branch was taken because that is the concept being taught.
        """
        target = ipaddress.IPv4Address(destination)

        # Same subnet — talk directly, no gateway involved.
        for interface in device.interfaces.values():
            network = interface.network
            if network is None or not interface.enabled:
                continue
            if target in network:
                self.trace.add(
                    EventKind.ROUTE_LOOKUP,
                    device.id,
                    device.name,
                    f"{destination} is on the local subnet {network}",
                    interface=interface.name,
                    detail=(f"Reached directly through {interface.name}; no gateway is involved."),
                )
                return interface, destination

        # Different subnet — a router must carry it.
        route = self.network.lookup_route(device.id, destination)
        if route is None:
            enabled = [item for item in device.interfaces.values() if item.enabled]
            if not enabled:
                self.trace.fail(
                    device.id,
                    device.name,
                    "No interface is up",
                    "Every interface is administratively down — they need 'no shutdown'.",
                )
            else:
                self.trace.fail(
                    device.id,
                    device.name,
                    f"No route to {destination}",
                    self._no_route_detail(device, destination),
                )
            return None, None

        next_hop = route.next_hop or destination

        if route.source == "gateway":
            self.trace.add(
                EventKind.ROUTE_LOOKUP,
                device.id,
                device.name,
                f"{destination} is not local — sending to the gateway {next_hop}",
                detail="The destination is in another subnet, so the frame goes to the gateway.",
            )
        else:
            self.trace.add(
                EventKind.ROUTE_LOOKUP,
                device.id,
                device.name,
                f"Route to {route.network} via {route.source}",
                interface=route.interface,
                detail=(
                    f"Next hop {next_hop}"
                    if route.next_hop
                    else f"Directly connected on {route.interface}"
                ),
            )

        egress = self._interface_towards(device, route, next_hop)
        if egress is None:
            self.trace.fail(
                device.id,
                device.name,
                f"Cannot reach the next hop {next_hop}",
                (
                    f"No interface on {device.name} is in the same subnet as "
                    f"{next_hop}. The gateway address is probably wrong."
                ),
            )
            return None, None

        return egress, next_hop

    @staticmethod
    def _no_route_detail(device: SimDevice, destination: str) -> str:
        """Explain a routing failure precisely.

        A shut-down interface that *would* have matched is a different problem
        from a genuinely missing route, and telling a learner to "add a route"
        when the route exists would send them the wrong way.
        """
        target = ipaddress.IPv4Address(destination)

        for interface in device.interfaces.values():
            network = interface.network
            if network is not None and not interface.enabled and target in network:
                return (
                    f"{interface.name} is in {network} and would reach this "
                    "destination, but it is administratively down. It needs "
                    "'no shutdown'."
                )

        return (
            "This device has no matching route and no default gateway. "
            "A host needs a gateway; a router needs a route."
        )

    @staticmethod
    def _interface_towards(device: SimDevice, route: object, next_hop: str) -> SimInterface | None:
        """The interface facing the next hop."""
        named = getattr(route, "interface", None)
        if named and named in device.interfaces:
            candidate = device.interfaces[named]
            if candidate.enabled:
                return candidate

        target = ipaddress.IPv4Address(next_hop)
        for interface in device.interfaces.values():
            network = interface.network
            if network is not None and interface.enabled and target in network:
                return interface
        return None

    # ------------------------------------------------------------------ #
    # The walk
    # ------------------------------------------------------------------ #
    def deliver(
        self,
        source: SimDevice,
        destination_ip: str,
        *,
        protocol: str,
        payload: str = "",
    ) -> DeliveryOutcome:
        """Carry one packet from `source` to whoever owns `destination_ip`."""
        source_interface = next(
            (item for item in source.interfaces.values() if item.enabled and item.ip), None
        )
        if source_interface is None:
            self.trace.fail(
                source.id,
                source.name,
                "No usable interface",
                (
                    "This device has no interface that is both configured with an "
                    "IP address and enabled."
                ),
            )
            return DeliveryOutcome(
                delivered=False,
                reason="The source has no working IP interface.",
                hint="Give it an address and bring the interface up.",
            )

        current = source
        current_source_ip = source_interface.ip
        ttl = DEFAULT_TTL
        hops = 0

        while hops < MAX_HOPS:
            hops += 1

            # Arrived?
            if current.owns_address(destination_ip):
                self.trace.add(
                    EventKind.DELIVER,
                    current.id,
                    current.name,
                    f"{protocol} delivered to {destination_ip}",
                    detail=payload or None,
                    frame=FrameSummary(
                        source_ip=current_source_ip,
                        destination_ip=destination_ip,
                        protocol=protocol,
                        ttl=ttl,
                    ),
                )
                return DeliveryOutcome(delivered=True, hops=hops, final_device=current.id)

            egress, next_hop = self.choose_egress(current, destination_ip)
            if egress is None or next_hop is None:
                return DeliveryOutcome(
                    delivered=False,
                    reason=f"{current.name} could not forward the packet.",
                    hint=self._forwarding_hint(current, destination_ip),
                    hops=hops,
                    final_device=current.id,
                )

            destination_mac = self.resolve_arp(current, egress, next_hop)
            if destination_mac is None:
                return DeliveryOutcome(
                    delivered=False,
                    reason=f"{current.name} could not resolve {next_hop} to a MAC address.",
                    hint=(
                        "Check that the next device is powered, cabled with the right "
                        "cable, has that address, and that its interface is up."
                    ),
                    hops=hops,
                    final_device=current.id,
                )

            peer = self.network.peer_of(current.id, egress.name)
            if peer is None:
                self.trace.fail(
                    current.id,
                    current.name,
                    f"{egress.name} has no usable link",
                    "The cable is missing, disabled, or of the wrong type.",
                    interface=egress.name,
                )
                return DeliveryOutcome(
                    delivered=False,
                    reason=f"{egress.name} on {current.name} has no usable link.",
                    hops=hops,
                    final_device=current.id,
                )

            self.trace.add(
                EventKind.FORWARD,
                current.id,
                current.name,
                f"{protocol} out {egress.name} toward {next_hop}",
                interface=egress.name,
                link_id=self._link_id(current.id, egress.name),
                to_device_id=peer[0],
                to_interface=peer[1],
                frame=FrameSummary(
                    source_mac=egress.mac,
                    destination_mac=destination_mac,
                    source_ip=current_source_ip,
                    destination_ip=destination_ip,
                    protocol=protocol,
                    ttl=ttl,
                ),
            )

            # Follow the frame to whichever device terminates it — switches in
            # between forward without touching Layer 3.
            landed = self._traverse_switches(peer[0], peer[1], destination_mac)
            if landed is None:
                return DeliveryOutcome(
                    delivered=False,
                    reason="The frame was lost in the switched path.",
                    hops=hops,
                    final_device=current.id,
                )

            next_device = self.network.devices[landed]

            if next_device.routes_ip and not next_device.owns_address(destination_ip):
                ttl -= 1
                if ttl <= 0:
                    self.trace.fail(
                        next_device.id,
                        next_device.name,
                        "TTL expired in transit",
                        "The packet was forwarded too many times — check for a routing loop.",
                        kind=EventKind.TIMEOUT,
                    )
                    return DeliveryOutcome(
                        delivered=False,
                        reason="TTL expired — the packet is looping.",
                        hops=hops,
                        final_device=next_device.id,
                    )

            current = next_device

        return DeliveryOutcome(
            delivered=False,
            reason="The packet exceeded the hop limit.",
            hint="There is probably a routing loop between two devices.",
            hops=hops,
        )

    def _traverse_switches(
        self, device_id: str, interface: str, destination_mac: str
    ) -> str | None:
        """Follow a frame through switches to the device that terminates it."""
        seen: set[str] = set()
        current_device, current_interface = device_id, interface

        while current_device not in seen:
            seen.add(current_device)
            device = self.network.devices.get(current_device)
            if device is None:
                return None

            if not device.switches_frames:
                return current_device

            port = device.interfaces.get(current_interface)
            vlan = port.access_vlan if port and port.switchport_mode else None

            self.trace.add(
                EventKind.SWITCH_FORWARD,
                device.id,
                device.name,
                f"Switching frame toward {destination_mac}",
                interface=current_interface,
                detail=(
                    f"Received on {current_interface}"
                    + (f" in VLAN {vlan}" if port and port.switchport_mode else "")
                ),
            )

            # Find the port holding the destination MAC within this VLAN.
            target: tuple[str, str] | None = None
            for peer_device_id, peer_interface in self.network.flood_into(
                current_device, current_interface, vlan
            ):
                peer_device = self.network.devices.get(peer_device_id)
                if peer_device is None:
                    continue
                peer_port = peer_device.interfaces.get(peer_interface)
                if peer_port and peer_port.mac == destination_mac:
                    target = (peer_device_id, peer_interface)
                    break

            if target is None:
                self.trace.fail(
                    device.id,
                    device.name,
                    f"No port has {destination_mac}",
                    (
                        "The destination is not reachable in this VLAN. Check that "
                        "both ports are in the same VLAN and that the link is up."
                    ),
                    interface=current_interface,
                )
                return None

            current_device, current_interface = target

        return current_device

    @staticmethod
    def _forwarding_hint(device: SimDevice, destination: str) -> str:
        if device.is_endpoint and not device.config.default_gateway:
            return (
                f"{device.name} has no default gateway, so it cannot reach anything "
                "outside its own subnet."
            )
        if device.routes_ip:
            return (
                f"Add a route on {device.name} for {destination}, or a default route "
                "pointing at the next router."
            )
        return f"Check the default gateway configured on {device.name}."
