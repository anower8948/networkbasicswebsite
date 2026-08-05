"""Builds a simulatable network from a topology document and device configs.

This turns the *editable* representation — devices with positions, links with
cable types, per-device configuration — into the structures forwarding actually
needs: MAC addresses, broadcast domains, and routing tables.

Two deliberate simplifications, both documented where they bite:

* MAC addresses are derived deterministically from the device and interface
  name rather than allocated. A learner comparing two runs should see the same
  addresses, and a random MAC would make traces impossible to follow.
* Dynamic routing (OSPF, EIGRP, RIP) is resolved by flooding advertised
  networks across routers that share a protocol and a working link, rather than
  by running the real algorithms. Convergence, metrics and DR/BDR election are
  out of scope for a teaching simulator; reachability is what the lesson needs.
"""

from __future__ import annotations

import hashlib
import ipaddress
from collections import deque
from dataclasses import dataclass, field

from pydantic import ValidationError as SchemaValidationError

from app.core.exceptions import ValidationError
from app.models.enums import CableKind, DeviceKind
from app.schemas.device_config import DeviceConfig, admin_up
from app.schemas.topology import TopologyDevice, TopologyDocument, TopologyLink
from app.services.device_catalog import recommended_cable, spec_for

# Devices that make a Layer 3 forwarding decision.
ROUTING_KINDS = frozenset(
    {
        DeviceKind.ROUTER,
        DeviceKind.MULTILAYER_SWITCH,
        DeviceKind.FIREWALL,
        DeviceKind.WIRELESS_ROUTER,
        DeviceKind.ISP,
    }
)

# Devices that forward frames at Layer 2 without terminating them.
SWITCHING_KINDS = frozenset(
    {DeviceKind.SWITCH, DeviceKind.MULTILAYER_SWITCH, DeviceKind.ACCESS_POINT}
)


def derive_mac(device_id: str, interface: str) -> str:
    """A stable, locally administered MAC for one interface.

    The `02:` prefix marks it locally administered, which is what a simulator
    should use — it can never collide with a real burned-in address.
    """
    digest = hashlib.sha256(f"{device_id}:{interface}".encode()).hexdigest()
    octets = [digest[index : index + 2] for index in range(0, 10, 2)]
    return ":".join(["02", *octets]).upper()


@dataclass(slots=True)
class SimInterface:
    device_id: str
    name: str
    mac: str
    enabled: bool
    ip: str | None = None
    mask: str | None = None
    dhcp: bool = False
    switchport_mode: str | None = None
    access_vlan: int = 1
    allowed_vlans: list[int] = field(default_factory=list)
    native_vlan: int = 1
    acl_in: str | None = None
    acl_out: str | None = None
    nat_side: str | None = None

    @property
    def network(self) -> ipaddress.IPv4Network | None:
        if not (self.ip and self.mask):
            return None
        return ipaddress.IPv4Interface(f"{self.ip}/{self.mask}").network

    def carries_vlan(self, vlan: int) -> bool:
        """Whether a frame in this VLAN may leave this port."""
        if self.switchport_mode == "trunk":
            # An empty allow-list means all VLANs, as on real hardware.
            return not self.allowed_vlans or vlan in self.allowed_vlans
        return self.access_vlan == vlan


@dataclass(slots=True)
class SimDevice:
    id: str
    name: str
    kind: DeviceKind
    config: DeviceConfig
    interfaces: dict[str, SimInterface]

    @property
    def routes_ip(self) -> bool:
        return self.kind in ROUTING_KINDS

    @property
    def switches_frames(self) -> bool:
        return self.kind in SWITCHING_KINDS

    @property
    def is_endpoint(self) -> bool:
        return spec_for(self.kind).is_endpoint

    def interface_holding(self, address: str) -> SimInterface | None:
        """The interface configured with this exact address."""
        return next((item for item in self.interfaces.values() if item.ip == address), None)

    def owns_address(self, address: str) -> bool:
        return self.interface_holding(address) is not None

    def interface_for_network(self, target: str) -> SimInterface | None:
        """The interface whose subnet contains `target`."""
        wanted = ipaddress.IPv4Address(target)
        for item in self.interfaces.values():
            network = item.network
            if network is not None and wanted in network:
                return item
        return None


@dataclass(slots=True)
class Route:
    """One routing-table entry."""

    network: ipaddress.IPv4Network
    source: str  # connected | static | ospf | eigrp | rip
    interface: str | None = None
    next_hop: str | None = None
    distance: int = 0

    @property
    def prefix_length(self) -> int:
        return self.network.prefixlen


@dataclass(slots=True)
class SimLink:
    id: str
    a_device: str
    a_interface: str
    b_device: str
    b_interface: str
    cable: CableKind
    enabled: bool
    # A miscabled link does not pass traffic — the Part 4 warning becomes a
    # real failure here, which is the whole point of flagging it then.
    cable_ok: bool

    def peer(self, device_id: str, interface: str) -> tuple[str, str] | None:
        if self.a_device == device_id and self.a_interface == interface:
            return self.b_device, self.b_interface
        if self.b_device == device_id and self.b_interface == interface:
            return self.a_device, self.a_interface
        return None

    @property
    def usable(self) -> bool:
        return self.enabled and self.cable_ok


class Network:
    """A topology resolved into something forwarding can run over."""

    def __init__(self, document: TopologyDocument) -> None:
        self.devices: dict[str, SimDevice] = {}
        self.links: dict[str, SimLink] = {}
        # (device_id, interface) -> link id
        self._port_link: dict[tuple[str, str], str] = {}
        self._routing_cache: dict[str, list[Route]] = {}

        for device in document.devices:
            self.devices[device.id] = self._build_device(device)

        for link in document.links:
            self.links[link.id] = self._build_link(link)
            self._port_link[(link.source.device_id, link.source.interface)] = link.id
            self._port_link[(link.target.device_id, link.target.interface)] = link.id

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #
    @staticmethod
    def _build_device(device: TopologyDevice) -> SimDevice:
        # A document carries device configs as free-form JSON — it may have been
        # exported by an older build or hand-edited before import. A config the
        # simulator cannot read is the learner's problem to fix, so name the
        # device rather than letting a schema error surface as a server fault.
        try:
            config = DeviceConfig.model_validate(device.config or {})
        except SchemaValidationError as error:
            fields = ", ".join(str(item["loc"][-1]) for item in error.errors() if item.get("loc"))
            raise ValidationError(
                f"The configuration on {device.name} cannot be read"
                + (f" — check: {fields}." if fields else ".")
            ) from error

        interfaces: dict[str, SimInterface] = {}

        for entry in spec_for(device.kind).interfaces():
            name = str(entry["name"])
            if not entry["connectable"]:
                continue
            configured = config.interfaces.get(name)

            interfaces[name] = SimInterface(
                device_id=device.id,
                name=name,
                mac=derive_mac(device.id, name),
                enabled=admin_up(configured, device.kind.value),
                ip=configured.ip_address if configured else None,
                mask=configured.subnet_mask if configured else None,
                dhcp=bool(configured and configured.dhcp),
                switchport_mode=configured.switchport_mode if configured else None,
                access_vlan=(configured.access_vlan if configured else None) or 1,
                allowed_vlans=list(configured.allowed_vlans) if configured else [],
                native_vlan=(configured.native_vlan if configured else None) or 1,
                acl_in=configured.acl_in if configured else None,
                acl_out=configured.acl_out if configured else None,
                nat_side=configured.nat_side if configured else None,
            )

        return SimDevice(
            id=device.id,
            name=device.name,
            kind=device.kind,
            config=config,
            interfaces=interfaces,
        )

    def _build_link(self, link: TopologyLink) -> SimLink:
        source_kind = self.devices[link.source.device_id].kind
        target_kind = self.devices[link.target.device_id].kind
        expected = recommended_cable(
            source_kind, link.source.interface, target_kind, link.target.interface
        )
        # Fibre is accepted anywhere the optics would match, as in Part 4.
        cable_ok = link.cable is expected or link.cable is CableKind.FIBER

        return SimLink(
            id=link.id,
            a_device=link.source.device_id,
            a_interface=link.source.interface,
            b_device=link.target.device_id,
            b_interface=link.target.interface,
            cable=link.cable,
            enabled=link.enabled,
            cable_ok=cable_ok,
        )

    # ------------------------------------------------------------------ #
    # Topology queries
    # ------------------------------------------------------------------ #
    def link_on(self, device_id: str, interface: str) -> SimLink | None:
        link_id = self._port_link.get((device_id, interface))
        return self.links.get(link_id) if link_id else None

    def peer_of(self, device_id: str, interface: str) -> tuple[str, str] | None:
        """The far end of the cable, if there is a usable one."""
        link = self.link_on(device_id, interface)
        if link is None or not link.usable:
            return None
        return link.peer(device_id, interface)

    def device_by_name(self, name: str) -> SimDevice | None:
        lowered = name.lower()
        return next(
            (device for device in self.devices.values() if device.name.lower() == lowered),
            None,
        )

    def device_owning(self, address: str) -> SimDevice | None:
        """Which device holds this IP on one of its interfaces."""
        return next(
            (device for device in self.devices.values() if device.owns_address(address)),
            None,
        )

    # ------------------------------------------------------------------ #
    # Layer 2
    # ------------------------------------------------------------------ #
    def broadcast_domain(
        self, device_id: str, interface: str, vlan: int | None = None
    ) -> list[tuple[str, str]]:
        """Every port a broadcast *sent out of* this port would reach.

        `vlan` is None for a host, which has no VLAN concept — the frame takes
        the VLAN of whichever switch access port it arrives on.
        """
        start = self.peer_of(device_id, interface)
        return self._flood([start] if start else [], vlan, {(device_id, interface)})

    def flood_into(
        self, device_id: str, ingress: str, vlan: int | None = None
    ) -> list[tuple[str, str]]:
        """Every port a frame *arriving on* this port would be flooded to.

        Distinct from `broadcast_domain`, and the distinction matters: that one
        answers "where does my broadcast go", this one answers "a switch has a
        frame on port X, where can it send it" — which means every *other* port
        on that switch, not the peer of X.
        """
        device = self.devices.get(device_id)
        if device is None:
            return []

        # The frame's VLAN comes from the port it arrived on.
        ingress_port = device.interfaces.get(ingress)
        if vlan is None and ingress_port and ingress_port.switchport_mode == "access":
            vlan = ingress_port.access_vlan

        seeds: list[tuple[str, str]] = []
        for name, port in device.interfaces.items():
            if name == ingress or not port.enabled:
                continue
            if vlan is not None and port.switchport_mode and not port.carries_vlan(vlan):
                continue
            peer = self.peer_of(device_id, name)
            if peer is not None:
                seeds.append(peer)

        return self._flood(seeds, vlan, {(device_id, ingress)})

    def _flood(
        self,
        seeds: list[tuple[str, str]],
        vlan: int | None,
        visited: set[tuple[str, str]],
    ) -> list[tuple[str, str]]:
        """Breadth-first walk through switches, stopping where frames terminate.

        `vlan` may start as None — a host does not tag its frames. The first
        switch access port the frame reaches decides the VLAN, and every port
        after that must carry it. This is what makes a VLAN a separate
        broadcast domain rather than a label the sender chooses.
        """
        reached: list[tuple[str, str]] = []
        seen = set(visited)
        # Each queued port carries the VLAN the frame has by the time it lands.
        queue: deque[tuple[str, str, int | None]] = deque(
            (device, interface, vlan) for device, interface in seeds
        )

        while queue:
            current_device, current_interface, current_vlan = queue.popleft()
            if (current_device, current_interface) in seen:
                continue
            seen.add((current_device, current_interface))

            device = self.devices.get(current_device)
            if device is None:
                continue
            port = device.interfaces.get(current_interface)
            if port is None or not port.enabled:
                continue

            if device.switches_frames and port.switchport_mode == "access":
                if current_vlan is None:
                    # An untagged frame takes this access port's VLAN.
                    current_vlan = port.access_vlan
                elif port.access_vlan != current_vlan:
                    continue  # wrong VLAN — the port drops it
            elif (
                device.switches_frames
                and port.switchport_mode == "trunk"
                and current_vlan is not None
                and not port.carries_vlan(current_vlan)
            ):
                continue

            reached.append((current_device, current_interface))

            if not device.switches_frames:
                # Hosts and routers consume the frame rather than flooding it.
                continue

            for name, other in device.interfaces.items():
                if name == current_interface or not other.enabled:
                    continue
                if (
                    current_vlan is not None
                    and other.switchport_mode
                    and not other.carries_vlan(current_vlan)
                ):
                    continue
                peer = self.peer_of(current_device, name)
                if peer is not None and peer not in seen:
                    queue.append((peer[0], peer[1], current_vlan))

        return reached

    def blocked_links_near(self, device_id: str, interface: str) -> list[SimLink]:
        """Unusable links on the segment behind this port.

        When ARP fails and the target *does* exist, the cause is almost always a
        link that cannot pass traffic — miscabled or unplugged — somewhere along
        the switched path. Blaming VLANs would send the learner the wrong way.
        """
        blocked: list[SimLink] = []
        seen: set[str] = set()
        queue: deque[str] = deque([device_id])

        while queue:
            current = queue.popleft()
            if current in seen:
                continue
            seen.add(current)

            device = self.devices.get(current)
            if device is None:
                continue

            for name in device.interfaces:
                link = self.link_on(current, name)
                if link is None:
                    continue
                if not link.usable:
                    if link not in blocked:
                        blocked.append(link)
                    continue
                peer = link.peer(current, name)
                # Keep walking only through switches — a router terminates the
                # broadcast domain, so anything beyond it is a different problem.
                if peer and peer[0] not in seen and self.devices[peer[0]].switches_frames:
                    queue.append(peer[0])

        return blocked

    # ------------------------------------------------------------------ #
    # Layer 3
    # ------------------------------------------------------------------ #
    def routing_table(self, device_id: str) -> list[Route]:
        """Connected, static and dynamically advertised routes, longest-prefix first."""
        if device_id in self._routing_cache:
            return self._routing_cache[device_id]

        device = self.devices[device_id]
        routes: list[Route] = []

        for interface in device.interfaces.values():
            network = interface.network
            if network is not None and interface.enabled:
                routes.append(Route(network=network, source="connected", interface=interface.name))

        for static in device.config.static_routes:
            try:
                network = ipaddress.IPv4Network(f"{static.network}/{static.mask}", strict=False)
            except ValueError:
                continue
            routes.append(
                Route(
                    network=network,
                    source="static",
                    next_hop=static.next_hop,
                    interface=static.exit_interface,
                    distance=static.distance,
                )
            )

        routes.extend(self._dynamic_routes(device_id))

        # Longest prefix wins; among equals, prefer the lower distance.
        routes.sort(key=lambda route: (-route.prefix_length, route.distance))
        self._routing_cache[device_id] = routes
        return routes

    def _dynamic_routes(self, device_id: str) -> list[Route]:
        """Networks learned from routers sharing a protocol.

        A reachability approximation, not a protocol implementation: every
        router running the same protocol, reachable over usable links, shares
        the networks it advertises. Enough for "can this ping succeed", which is
        what the lesson is about; metrics and convergence are not modelled.
        """
        device = self.devices[device_id]
        protocols = {
            name
            for name, value in (
                ("ospf", device.config.ospf),
                ("eigrp", device.config.eigrp),
                ("rip", device.config.rip),
            )
            if value is not None
        }
        if not protocols:
            return []

        learned: list[Route] = []
        own_networks = {
            interface.network for interface in device.interfaces.values() if interface.network
        }

        for peer_id in self._routing_peers(device_id, protocols):
            peer = self.devices[peer_id]
            next_hop = self._next_hop_towards(device_id, peer_id)
            if next_hop is None:
                continue

            for interface in peer.interfaces.values():
                network = interface.network
                if network is None or not interface.enabled or network in own_networks:
                    continue
                if not self._advertises(peer, network):
                    continue
                learned.append(
                    Route(
                        network=network,
                        source=sorted(protocols)[0],
                        next_hop=next_hop[0],
                        interface=next_hop[1],
                        distance=110,
                    )
                )

        return learned

    @staticmethod
    def _advertises(device: SimDevice, network: ipaddress.IPv4Network) -> bool:
        """Whether a router's protocol configuration covers this network."""
        config = device.config

        if config.ospf:
            for entry in config.ospf.networks:
                wildcard = int(ipaddress.IPv4Address(entry.wildcard))
                mask = ~wildcard & 0xFFFFFFFF
                try:
                    advertised = ipaddress.IPv4Network(
                        f"{entry.network}/{ipaddress.IPv4Address(mask)}", strict=False
                    )
                except ValueError:
                    continue
                if network.subnet_of(advertised) or network == advertised:
                    return True

        if config.eigrp:
            for eigrp_entry in config.eigrp.networks:
                # A bare `network 10.0.0.0` covers the whole classful block.
                if network.network_address in ipaddress.IPv4Network(
                    f"{eigrp_entry.network}/8", strict=False
                ):
                    return True

        if config.rip:
            for rip_network in config.rip.networks:
                if network.network_address in ipaddress.IPv4Network(
                    f"{rip_network}/8", strict=False
                ):
                    return True

        return False

    def _routing_peers(self, device_id: str, protocols: set[str]) -> list[str]:
        """Routers reachable over usable links that run a shared protocol."""
        peers: list[str] = []
        seen = {device_id}
        queue: deque[str] = deque([device_id])

        while queue:
            current = queue.popleft()
            device = self.devices[current]
            for name, interface in device.interfaces.items():
                if not interface.enabled:
                    continue
                peer = self.peer_of(current, name)
                if peer is None:
                    continue
                peer_device = self.devices[peer[0]]
                if peer[0] in seen:
                    continue

                if peer_device.switches_frames:
                    # Traverse switches — they join routers into one segment.
                    seen.add(peer[0])
                    queue.append(peer[0])
                    continue

                if not peer_device.routes_ip:
                    continue

                peer_protocols = {
                    label
                    for label, value in (
                        ("ospf", peer_device.config.ospf),
                        ("eigrp", peer_device.config.eigrp),
                        ("rip", peer_device.config.rip),
                    )
                    if value is not None
                }
                if peer_protocols & protocols:
                    seen.add(peer[0])
                    peers.append(peer[0])
                    queue.append(peer[0])

        return peers

    def _next_hop_towards(self, device_id: str, target_device: str) -> tuple[str, str] | None:
        """The neighbour address and exit interface toward another router."""
        device = self.devices[device_id]
        target = self.devices[target_device]

        for name, interface in device.interfaces.items():
            network = interface.network
            if network is None or not interface.enabled:
                continue
            for peer_interface in target.interfaces.values():
                peer_network = peer_interface.network
                if peer_network is None or not peer_interface.enabled:
                    continue
                if peer_network == network and peer_interface.ip:
                    return peer_interface.ip, name

        return None

    def lookup_route(self, device_id: str, destination: str) -> Route | None:
        """Longest-prefix match, falling back to the device's default gateway."""
        target = ipaddress.IPv4Address(destination)

        for route in self.routing_table(device_id):
            if target in route.network:
                return route

        # Hosts and Layer 2 switches have a gateway rather than a table.
        gateway = self.devices[device_id].config.default_gateway
        if gateway:
            return Route(
                network=ipaddress.IPv4Network("0.0.0.0/0"),
                source="gateway",
                next_hop=gateway,
            )

        return None
