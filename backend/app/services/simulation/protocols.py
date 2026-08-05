"""Protocol flows built on the forwarder.

Each runs a realistic exchange and produces a trace a learner can read:

* **ICMP** — echo request and reply, plus traceroute by increasing TTL.
* **ARP** — the resolution alone, useful for teaching Layer 2 on its own.
* **DHCP** — the full DORA exchange against a router pool or a server.
* **DNS** — a query to the configured resolver, answered from its host records.
* **TCP** — three-way handshake, data, and an orderly four-way close.
* **UDP** — a single datagram, deliberately with no handshake and no reply.

The point of modelling TCP and UDP separately is that the *difference* is the
lesson: TCP costs three round trips before a byte of data moves, UDP costs none.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass

from app.schemas.device_config import DhcpPool
from app.services.simulation.forwarding import Forwarder
from app.services.simulation.network import Network, SimDevice, SimInterface
from app.services.simulation.trace import (
    EventKind,
    FrameSummary,
    SimulationResult,
    TraceBuilder,
)


@dataclass(slots=True)
class Target:
    """A resolved simulation endpoint."""

    device: SimDevice
    address: str


class Simulator:
    """Runs one protocol exchange over a network."""

    def __init__(self, network: Network) -> None:
        self.network = network
        self.trace = TraceBuilder()
        self.forwarder = Forwarder(network, self.trace)

    # ------------------------------------------------------------------ #
    # ICMP
    # ------------------------------------------------------------------ #
    def ping(self, source_id: str, destination: str, count: int = 4) -> SimulationResult:
        """ICMP echo request and reply."""
        source = self.network.devices.get(source_id)
        if source is None:
            return self._unknown_source("ICMP")

        resolved = self._resolve_destination(source, destination)
        if resolved is None:
            return SimulationResult(
                success=False,
                protocol="ICMP",
                summary=f"Ping to {destination} failed",
                failure_reason=f"Nothing in this topology answers to {destination}.",
                hint="Check the address, or configure it on the device you meant.",
                events=self.trace.events,
            )

        self.trace.add(
            EventKind.NOTE,
            source.id,
            source.name,
            f"Pinging {resolved.address} with {count} echo requests",
        )

        outcome = self.forwarder.deliver(source, resolved.address, protocol="ICMP echo request")
        if not outcome.delivered:
            return SimulationResult(
                success=False,
                protocol="ICMP",
                summary=f"Ping to {resolved.address} failed — request timed out",
                failure_reason=outcome.reason,
                hint=outcome.hint,
                events=self.trace.events,
            )

        # The reply is a separate packet travelling the other way. Simulating it
        # matters: a one-way path is a real failure mode, and a learner who has
        # only configured a route outbound needs to see the return leg fail.
        target_device = self.network.devices[outcome.final_device or resolved.device.id]
        source_address = self._address_facing(source, resolved.address)

        self.trace.add(
            EventKind.REPLY,
            target_device.id,
            target_device.name,
            f"Echo reply to {source_address}",
            frame=FrameSummary(
                source_ip=resolved.address,
                destination_ip=source_address,
                protocol="ICMP echo reply",
            ),
        )

        return_outcome = self.forwarder.deliver(
            target_device, source_address or "", protocol="ICMP echo reply"
        )
        if not return_outcome.delivered:
            return SimulationResult(
                success=False,
                protocol="ICMP",
                summary="Request reached the destination, but the reply could not get back",
                failure_reason=(
                    f"{target_device.name} received the ping but cannot route the "
                    f"reply to {source_address}. {return_outcome.reason or ''}".strip()
                ),
                hint=(
                    "A path must work in both directions. Check the return route or "
                    f"default gateway on {target_device.name}."
                ),
                events=self.trace.events,
            )

        return SimulationResult(
            success=True,
            protocol="ICMP",
            summary=(
                f"Reply from {resolved.address}: {count}/{count} received, "
                f"{outcome.hops} hop{'s' if outcome.hops != 1 else ''}"
            ),
            events=self.trace.events,
        )

    def traceroute(self, source_id: str, destination: str) -> SimulationResult:
        """Discover the path by letting the TTL expire at each hop."""
        source = self.network.devices.get(source_id)
        if source is None:
            return self._unknown_source("ICMP")

        resolved = self._resolve_destination(source, destination)
        if resolved is None:
            return SimulationResult(
                success=False,
                protocol="traceroute",
                summary=f"Cannot trace a route to {destination}",
                failure_reason=f"Nothing in this topology answers to {destination}.",
                events=self.trace.events,
            )

        self.trace.add(
            EventKind.NOTE,
            source.id,
            source.name,
            f"Tracing the route to {resolved.address}",
            detail="Each hop is found by sending a packet whose TTL expires there.",
        )

        outcome = self.forwarder.deliver(source, resolved.address, protocol="traceroute probe")
        if not outcome.delivered:
            return SimulationResult(
                success=False,
                protocol="traceroute",
                summary=f"Trace to {resolved.address} did not complete",
                failure_reason=outcome.reason,
                hint=outcome.hint,
                events=self.trace.events,
            )

        return SimulationResult(
            success=True,
            protocol="traceroute",
            summary=f"Reached {resolved.address} in {outcome.hops} hop"
            + ("s" if outcome.hops != 1 else ""),
            events=self.trace.events,
        )

    def arp(self, source_id: str, destination: str) -> SimulationResult:
        """Resolve one address to a MAC, and nothing more."""
        source = self.network.devices.get(source_id)
        if source is None:
            return self._unknown_source("ARP")

        egress, next_hop = self.forwarder.choose_egress(source, destination)
        if egress is None or next_hop is None:
            return SimulationResult(
                success=False,
                protocol="ARP",
                summary=f"Cannot ARP for {destination}",
                failure_reason=f"{source.name} has no interface facing {destination}.",
                events=self.trace.events,
            )

        mac = self.forwarder.resolve_arp(source, egress, next_hop)
        if mac is None:
            return SimulationResult(
                success=False,
                protocol="ARP",
                summary=f"No reply for {next_hop}",
                failure_reason=f"Nothing on the segment answered for {next_hop}.",
                hint="Check cabling, VLANs, and that the target interface is up.",
                events=self.trace.events,
            )

        return SimulationResult(
            success=True,
            protocol="ARP",
            summary=f"{next_hop} is at {mac}",
            events=self.trace.events,
        )

    # ------------------------------------------------------------------ #
    # DHCP
    # ------------------------------------------------------------------ #
    def dhcp(self, source_id: str) -> SimulationResult:
        """The DORA exchange: Discover, Offer, Request, Acknowledge."""
        client = self.network.devices.get(source_id)
        if client is None:
            return self._unknown_source("DHCP")

        interface = next((item for item in client.interfaces.values() if item.enabled), None)
        if interface is None:
            return SimulationResult(
                success=False,
                protocol="DHCP",
                summary="DHCP failed — no interface is up",
                failure_reason=f"Every interface on {client.name} is administratively down.",
                hint="Bring an interface up before requesting an address.",
                events=self.trace.events,
            )

        self.trace.add(
            EventKind.DHCP_DISCOVER,
            client.id,
            client.name,
            "DHCP Discover (broadcast)",
            interface=interface.name,
            link_id=self.forwarder._link_id(client.id, interface.name),  # noqa: SLF001
            detail="The client has no address yet, so it broadcasts to 255.255.255.255.",
            frame=FrameSummary(
                source_mac=interface.mac,
                destination_mac="FF:FF:FF:FF:FF:FF",
                source_ip="0.0.0.0",
                destination_ip="255.255.255.255",
                protocol="DHCP",
            ),
        )

        server, pool = self._find_dhcp_pool(client, interface)
        if server is None or pool is None:
            return SimulationResult(
                success=False,
                protocol="DHCP",
                summary="DHCP failed — no server responded",
                failure_reason=(
                    "No DHCP pool serving this segment answered the Discover. "
                    "A client with no answer self-assigns a 169.254.x.x APIPA address."
                ),
                hint=(
                    "Configure a DHCP pool on the router for this subnet, and check "
                    "that the client is in the same broadcast domain as the server."
                ),
                events=self.trace.events,
            )

        offered = self._offer_address(pool)
        self.trace.add(
            EventKind.DHCP_OFFER,
            server.id,
            server.name,
            f"DHCP Offer: {offered}",
            detail=(
                f"From pool '{pool.name}' — mask {pool.mask}"
                + (f", gateway {pool.gateway}" if pool.gateway else "")
            ),
            frame=FrameSummary(
                source_ip=self._pool_server_address(server, pool),
                destination_ip="255.255.255.255",
                protocol="DHCP",
            ),
        )
        self.trace.add(
            EventKind.DHCP_REQUEST,
            client.id,
            client.name,
            f"DHCP Request for {offered}",
            interface=interface.name,
            detail="Still broadcast, so any other offering servers know it was declined.",
        )
        self.trace.add(
            EventKind.DHCP_ACK,
            server.id,
            server.name,
            f"DHCP Ack — {offered} leased for {pool.lease_hours} hours",
            detail=(
                f"Address {offered}, mask {pool.mask}"
                + (f", gateway {pool.gateway}" if pool.gateway else "")
                + (f", DNS {', '.join(pool.dns_servers)}" if pool.dns_servers else "")
            ),
        )

        return SimulationResult(
            success=True,
            protocol="DHCP",
            summary=f"{client.name} leased {offered} from {server.name}",
            events=self.trace.events,
        )

    def _find_dhcp_pool(
        self, client: SimDevice, interface: SimInterface
    ) -> tuple[SimDevice | None, DhcpPool | None]:
        """Find a device with a pool serving the client's broadcast domain."""
        vlan = interface.access_vlan if interface.switchport_mode else 1
        reachable = {
            device_id
            for device_id, _ in self.network.broadcast_domain(client.id, interface.name, vlan)
        }

        for device_id in reachable:
            device = self.network.devices.get(device_id)
            if device is None:
                continue
            for pool in device.config.dhcp_pools:
                # A pool serves the segment if one of the device's own
                # interfaces sits in the pool's network.
                try:
                    pool_network = ipaddress.IPv4Network(
                        f"{pool.network}/{pool.mask}", strict=False
                    )
                except ValueError:
                    continue
                for candidate in device.interfaces.values():
                    if (
                        candidate.enabled
                        and candidate.ip
                        and ipaddress.IPv4Address(candidate.ip) in pool_network
                    ):
                        return device, pool

        return None, None

    @staticmethod
    def _offer_address(pool: DhcpPool) -> str:
        """First usable address in the pool, skipping any excluded range."""
        network = ipaddress.IPv4Network(f"{pool.network}/{pool.mask}", strict=False)
        excluded_end = getattr(pool, "excluded_end", None)
        gateway = getattr(pool, "gateway", None)

        start = network.network_address + 1
        if excluded_end:
            start = max(start, ipaddress.IPv4Address(excluded_end) + 1)

        candidate = start
        while candidate < network.broadcast_address:
            if not gateway or str(candidate) != gateway:
                return str(candidate)
            candidate += 1
        return str(start)

    @staticmethod
    def _pool_server_address(server: SimDevice, pool: DhcpPool) -> str | None:
        network = ipaddress.IPv4Network(f"{pool.network}/{pool.mask}", strict=False)
        for interface in server.interfaces.values():
            if interface.ip and ipaddress.IPv4Address(interface.ip) in network:
                return interface.ip
        return None

    # ------------------------------------------------------------------ #
    # DNS
    # ------------------------------------------------------------------ #
    def dns(self, source_id: str, hostname: str) -> SimulationResult:
        """Resolve a name using the device's configured DNS server."""
        client = self.network.devices.get(source_id)
        if client is None:
            return self._unknown_source("DNS")

        servers = client.config.dns_servers
        if not servers:
            return SimulationResult(
                success=False,
                protocol="DNS",
                summary=f"Cannot resolve {hostname}",
                failure_reason=f"{client.name} has no DNS server configured.",
                hint="Set a DNS server on the device, or hand one out over DHCP.",
                events=self.trace.events,
            )

        resolver = servers[0]
        self.trace.add(
            EventKind.DNS_QUERY,
            client.id,
            client.name,
            f"DNS query: {hostname} to {resolver}",
            detail="A UDP query on port 53.",
        )

        outcome = self.forwarder.deliver(client, resolver, protocol="DNS query")
        if not outcome.delivered:
            return SimulationResult(
                success=False,
                protocol="DNS",
                summary=f"Cannot reach the DNS server {resolver}",
                failure_reason=outcome.reason,
                hint=(
                    "Names cannot resolve if the resolver is unreachable — try "
                    "pinging its address first."
                ),
                events=self.trace.events,
            )

        # A device answers for its own name, which is enough to demonstrate
        # resolution without inventing a zone file format.
        answer = self.network.device_by_name(hostname.split(".")[0])
        if answer is None:
            self.trace.fail(
                self.network.devices[outcome.final_device or resolver].id,
                self.network.devices[outcome.final_device or resolver].name,
                f"NXDOMAIN — no record for {hostname}",
                "The resolver has no record for that name.",
            )
            return SimulationResult(
                success=False,
                protocol="DNS",
                summary=f"{hostname} does not resolve",
                failure_reason=f"The resolver has no record for {hostname}.",
                hint="Names resolve to devices in this topology — try a device name.",
                events=self.trace.events,
            )

        address = next(
            (item.ip for item in answer.interfaces.values() if item.ip and item.enabled), None
        )
        if address is None:
            return SimulationResult(
                success=False,
                protocol="DNS",
                summary=f"{hostname} has no address",
                failure_reason=f"{answer.name} exists but has no usable IP address.",
                events=self.trace.events,
            )

        self.trace.add(
            EventKind.DNS_RESPONSE,
            answer.id,
            answer.name,
            f"DNS response: {hostname} is {address}",
        )

        return SimulationResult(
            success=True,
            protocol="DNS",
            summary=f"{hostname} resolves to {address}",
            events=self.trace.events,
        )

    # ------------------------------------------------------------------ #
    # TCP and UDP
    # ------------------------------------------------------------------ #
    def tcp(self, source_id: str, destination: str, port: int = 80) -> SimulationResult:
        """Three-way handshake, one data exchange, and an orderly close."""
        source = self.network.devices.get(source_id)
        if source is None:
            return self._unknown_source("TCP")

        resolved = self._resolve_destination(source, destination)
        if resolved is None:
            return SimulationResult(
                success=False,
                protocol="TCP",
                summary=f"Cannot open a connection to {destination}",
                failure_reason=f"Nothing in this topology answers to {destination}.",
                events=self.trace.events,
            )

        self.trace.add(
            EventKind.NOTE,
            source.id,
            source.name,
            f"Opening a TCP connection to {resolved.address}:{port}",
        )

        # Reachability is checked once — the handshake is only meaningful if a
        # packet can get there at all.
        outcome = self.forwarder.deliver(source, resolved.address, protocol=f"TCP SYN → :{port}")
        if not outcome.delivered:
            return SimulationResult(
                success=False,
                protocol="TCP",
                summary=f"Connection to {resolved.address}:{port} failed",
                failure_reason=outcome.reason,
                hint=outcome.hint,
                events=self.trace.events,
            )

        target = self.network.devices[outcome.final_device or resolved.device.id]
        source_address = self._address_facing(source, resolved.address)

        for kind, device, summary, detail in (
            (
                EventKind.TCP_SYN,
                source,
                f"SYN → {resolved.address}:{port}",
                "The client proposes a connection and its initial sequence number.",
            ),
            (
                EventKind.TCP_SYN_ACK,
                target,
                f"SYN-ACK → {source_address}",
                "The server acknowledges and sends its own sequence number.",
            ),
            (
                EventKind.TCP_ACK,
                source,
                f"ACK → {resolved.address}:{port}",
                "The connection is established; data can now flow.",
            ),
            (
                EventKind.TCP_DATA,
                source,
                f"Data → {resolved.address}:{port}",
                "Payload travels only after the handshake completes.",
            ),
            (
                EventKind.TCP_FIN,
                source,
                "FIN, ACK, FIN, ACK",
                "Closing takes four messages, not three — a favourite exam point.",
            ),
        ):
            self.trace.add(
                kind,
                device.id,
                device.name,
                summary,
                detail=detail,
                frame=FrameSummary(
                    source_ip=source_address if device.id == source.id else resolved.address,
                    destination_ip=resolved.address if device.id == source.id else source_address,
                    protocol="TCP",
                ),
            )

        return SimulationResult(
            success=True,
            protocol="TCP",
            summary=f"Connection to {resolved.address}:{port} established and closed cleanly",
            events=self.trace.events,
        )

    def udp(self, source_id: str, destination: str, port: int = 53) -> SimulationResult:
        """One datagram, no handshake, no acknowledgement."""
        source = self.network.devices.get(source_id)
        if source is None:
            return self._unknown_source("UDP")

        resolved = self._resolve_destination(source, destination)
        if resolved is None:
            return SimulationResult(
                success=False,
                protocol="UDP",
                summary=f"Cannot send to {destination}",
                failure_reason=f"Nothing in this topology answers to {destination}.",
                events=self.trace.events,
            )

        self.trace.add(
            EventKind.UDP_DATAGRAM,
            source.id,
            source.name,
            f"UDP datagram → {resolved.address}:{port}",
            detail=(
                "No handshake and no acknowledgement — the datagram is sent and "
                "forgotten. This is why voice and video use UDP."
            ),
        )

        outcome = self.forwarder.deliver(source, resolved.address, protocol=f"UDP → :{port}")
        if not outcome.delivered:
            return SimulationResult(
                success=False,
                protocol="UDP",
                summary=f"Datagram to {resolved.address}:{port} was lost",
                failure_reason=outcome.reason,
                hint=(
                    (outcome.hint or "")
                    + " With UDP the sender is never told — the loss is silent."
                ).strip(),
                events=self.trace.events,
            )

        return SimulationResult(
            success=True,
            protocol="UDP",
            summary=f"Datagram delivered to {resolved.address}:{port} (unacknowledged)",
            events=self.trace.events,
        )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _resolve_destination(self, source: SimDevice, destination: str) -> Target | None:
        """Accept an IP address or a device name."""
        try:
            ipaddress.IPv4Address(destination)
        except ipaddress.AddressValueError:
            named = self.network.device_by_name(destination)
            if named is None:
                return None
            address = next(
                (item.ip for item in named.interfaces.values() if item.ip and item.enabled),
                None,
            )
            return Target(device=named, address=address) if address else None

        owner = self.network.device_owning(destination)
        if owner is None:
            return None
        return Target(device=owner, address=destination)

    @staticmethod
    def _address_facing(device: SimDevice, destination: str) -> str | None:
        """The source address this device would use toward `destination`."""
        target = ipaddress.IPv4Address(destination)
        for interface in device.interfaces.values():
            network = interface.network
            if network is not None and interface.enabled and target in network:
                return interface.ip
        return next(
            (item.ip for item in device.interfaces.values() if item.ip and item.enabled), None
        )

    def _unknown_source(self, protocol: str) -> SimulationResult:
        return SimulationResult(
            success=False,
            protocol=protocol,
            summary="Unknown source device",
            failure_reason="That device is not in this topology.",
            events=self.trace.events,
        )
