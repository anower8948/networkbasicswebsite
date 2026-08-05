"""Lab grading.

Evaluates a lab's declarative rules against the learner's topology and reports,
per rule, what was checked and what was found.

Two decisions shape this module:

**Reachability is graded by actually simulating it.** A `ping` rule runs the
Part 7 engine rather than inspecting addresses and inferring. This means a lab
cannot pass with a network that merely *looks* right — and when it fails, the
simulator's own diagnosis becomes the feedback the student reads. There is only
one definition of "these two hosts can talk", and the simulator owns it.

**Every result explains itself.** `CheckResult.summary` says what was asked,
`detail` says what was found. A grader that returns booleans teaches nothing;
the point of failing is finding out why.

Devices are addressed by **name** in the authoring model — an author writes
"PC1", not a UUID — resolved case-insensitively, with a fall back to the device
id so a rule survives a rename it was written against.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from app.schemas.lab import (
    CheckResult,
    DeviceCountRule,
    DhcpLeaseRule,
    DhcpPoolRule,
    DnsRule,
    GatewayRule,
    HostnameRule,
    InSubnetRule,
    InterfaceAddressRule,
    LabObjective,
    LinkRule,
    NoPingRule,
    ObjectiveResult,
    PingRule,
    PortRule,
    StaticRouteRule,
    VlanRule,
)
from app.schemas.topology import TopologyDocument
from app.services.simulation import Network, Simulator
from app.services.simulation.network import SimDevice, SimInterface


@dataclass(slots=True)
class GradeReport:
    """Everything a graded run produces."""

    results: list[CheckResult]
    objectives: list[ObjectiveResult]
    points_earned: int
    points_possible: int

    @property
    def score_percent(self) -> float:
        if self.points_possible <= 0:
            return 0.0
        return round((self.points_earned / self.points_possible) * 100, 1)


class LabGrader:
    """Evaluates one lab's rules against one topology document."""

    def __init__(self, document: TopologyDocument) -> None:
        # One network for the whole run: parsing is the expensive part, and a
        # fresh `Simulator` per traffic rule is what keeps ARP caches from
        # leaking between checks.
        self.network = Network(document)

    # ------------------------------------------------------------------ #
    # Entry point
    # ------------------------------------------------------------------ #
    def grade(
        self,
        # `Sequence` rather than `list`: callers pass a concrete list of the
        # rule union, and an invariant `list[object]` would reject it.
        rules: Sequence[object],
        objectives: Sequence[LabObjective] | None = None,
    ) -> GradeReport:
        results = [self._check(rule) for rule in rules]
        earned = sum(result.points_earned for result in results)
        possible = sum(result.points_possible for result in results)
        return GradeReport(
            results=results,
            objectives=self._roll_up(results, objectives or []),
            points_earned=earned,
            points_possible=possible,
        )

    @staticmethod
    def _roll_up(
        results: list[CheckResult], objectives: Sequence[LabObjective]
    ) -> list[ObjectiveResult]:
        """Collapse rule results onto the checklist the student sees.

        An objective passes only when every rule tied to it passes — a
        half-configured VLAN is not half an objective.
        """
        rolled: list[ObjectiveResult] = []
        for objective in objectives:
            related = [item for item in results if item.objective_id == objective.id]
            if not related:
                # An objective with no rules is narrative only; treat the
                # student's word for it rather than failing them on it.
                rolled.append(
                    ObjectiveResult(
                        objective_id=objective.id,
                        title=objective.title,
                        passed=True,
                        points_earned=0,
                        points_possible=0,
                    )
                )
                continue
            rolled.append(
                ObjectiveResult(
                    objective_id=objective.id,
                    title=objective.title,
                    passed=all(item.passed for item in related),
                    points_earned=sum(item.points_earned for item in related),
                    points_possible=sum(item.points_possible for item in related),
                )
            )
        return rolled

    # ------------------------------------------------------------------ #
    # Dispatch
    # ------------------------------------------------------------------ #
    def _check(self, rule: object) -> CheckResult:
        handlers: dict[type, Callable[..., tuple[bool, str, str | None]]] = {
            PingRule: self._check_ping,
            NoPingRule: self._check_no_ping,
            DnsRule: self._check_dns,
            PortRule: self._check_port,
            DhcpLeaseRule: self._check_dhcp_lease,
            InterfaceAddressRule: self._check_interface_address,
            InSubnetRule: self._check_in_subnet,
            GatewayRule: self._check_gateway,
            HostnameRule: self._check_hostname,
            StaticRouteRule: self._check_static_route,
            VlanRule: self._check_vlan,
            DhcpPoolRule: self._check_dhcp_pool,
            DeviceCountRule: self._check_device_count,
            LinkRule: self._check_link,
        }
        handler = handlers.get(type(rule))
        if handler is None:  # pragma: no cover - the union makes this unreachable
            return self._result(rule, False, "Unknown rule type", None)

        passed, summary, detail = handler(rule)
        return self._result(rule, passed, summary, detail)

    @staticmethod
    def _result(rule: object, passed: bool, summary: str, detail: str | None) -> CheckResult:
        rule_id = str(getattr(rule, "id", "rule"))
        points = int(getattr(rule, "points", 0))
        # An author-supplied message replaces the generated one on failure, so a
        # lab can speak in its own voice where the generic text is too dry.
        message = getattr(rule, "message", None)
        return CheckResult(
            rule_id=rule_id,
            objective_id=getattr(rule, "objective_id", None),
            passed=passed,
            points_earned=points if passed else 0,
            points_possible=points,
            summary=summary,
            detail=detail if passed or not message else f"{message} {detail or ''}".strip(),
        )

    # ------------------------------------------------------------------ #
    # Resolution helpers
    # ------------------------------------------------------------------ #
    def _device(self, reference: str) -> SimDevice | None:
        """Find a device by name (case-insensitive) or by id."""
        wanted = reference.strip().lower()
        for device in self.network.devices.values():
            if device.name.strip().lower() == wanted:
                return device
        return self.network.devices.get(reference)

    def _interface(self, device: SimDevice, name: str) -> SimInterface | None:
        direct = device.interfaces.get(name)
        if direct is not None:
            return direct
        wanted = name.strip().lower()
        return next(
            (item for item in device.interfaces.values() if item.name.lower() == wanted), None
        )

    @staticmethod
    def _missing(reference: str) -> tuple[bool, str, str | None]:
        return (
            False,
            f"{reference} must exist in the topology",
            f"There is no device called {reference}. Check the name, or add it.",
        )

    # ------------------------------------------------------------------ #
    # Traffic rules — graded by simulating, never by inspecting
    # ------------------------------------------------------------------ #
    def _check_ping(self, rule: PingRule) -> tuple[bool, str, str | None]:
        source = self._device(rule.source)
        if source is None:
            return self._missing(rule.source)

        result = Simulator(self.network).ping(source.id, rule.destination)
        summary = f"{rule.source} must be able to reach {rule.destination}"
        if result.success:
            return True, summary, result.summary
        # The simulator's own diagnosis is better feedback than anything the
        # grader could invent, so it is passed straight through.
        detail = " ".join(filter(None, [result.failure_reason, result.hint]))
        return False, summary, detail or result.summary

    def _check_no_ping(self, rule: NoPingRule) -> tuple[bool, str, str | None]:
        source = self._device(rule.source)
        if source is None:
            return self._missing(rule.source)

        result = Simulator(self.network).ping(source.id, rule.destination)
        summary = f"{rule.source} must NOT be able to reach {rule.destination}"
        if result.success:
            return (
                False,
                summary,
                f"Traffic got through: {result.summary}. These two must be separated.",
            )
        return True, summary, "Traffic is correctly blocked."

    def _check_dns(self, rule: DnsRule) -> tuple[bool, str, str | None]:
        source = self._device(rule.source)
        if source is None:
            return self._missing(rule.source)

        result = Simulator(self.network).dns(source.id, rule.hostname)
        summary = f"{rule.source} must be able to resolve {rule.hostname}"
        if result.success:
            return True, summary, result.summary
        return False, summary, " ".join(filter(None, [result.failure_reason, result.hint]))

    def _check_port(self, rule: PortRule) -> tuple[bool, str, str | None]:
        source = self._device(rule.source)
        if source is None:
            return self._missing(rule.source)

        result = Simulator(self.network).tcp(source.id, rule.destination, rule.port)
        summary = f"{rule.source} must reach {rule.destination} on TCP {rule.port}"
        if result.success:
            return True, summary, result.summary
        return False, summary, " ".join(filter(None, [result.failure_reason, result.hint]))

    def _check_dhcp_lease(self, rule: DhcpLeaseRule) -> tuple[bool, str, str | None]:
        source = self._device(rule.source)
        if source is None:
            return self._missing(rule.source)

        result = Simulator(self.network).dhcp(source.id)
        summary = f"{rule.source} must be able to lease an address over DHCP"
        if result.success:
            return True, summary, result.summary
        return False, summary, " ".join(filter(None, [result.failure_reason, result.hint]))

    # ------------------------------------------------------------------ #
    # Configuration rules
    # ------------------------------------------------------------------ #
    def _check_interface_address(self, rule: InterfaceAddressRule) -> tuple[bool, str, str | None]:
        device = self._device(rule.device)
        if device is None:
            return self._missing(rule.device)

        interface = self._interface(device, rule.interface)
        wanted = rule.address or "an address"
        summary = f"{rule.device} {rule.interface} must be configured with {wanted}"
        if interface is None:
            return False, summary, f"{device.name} has no interface called {rule.interface}."

        if rule.address is not None and interface.ip != rule.address:
            found = interface.ip or "nothing"
            return False, summary, f"It is configured with {found}."
        if rule.address is None and not interface.ip:
            return False, summary, "It has no address configured."
        if rule.mask is not None and interface.mask != rule.mask:
            return False, summary, f"The mask is {interface.mask or 'unset'}, expected {rule.mask}."
        if rule.enabled is not None and interface.enabled is not rule.enabled:
            state = "up" if interface.enabled else "administratively down"
            fix = "It needs 'no shutdown'." if rule.enabled else "It should be shut."
            return False, summary, f"The interface is {state}. {fix}"

        return True, summary, f"{interface.ip}/{interface.mask} and the interface is up."

    def _check_in_subnet(self, rule: InSubnetRule) -> tuple[bool, str, str | None]:
        device = self._device(rule.device)
        if device is None:
            return self._missing(rule.device)

        try:
            network = ipaddress.IPv4Network(rule.network, strict=False)
        except ValueError:
            return False, f"{rule.network} must be a valid subnet", "The lab's rule is malformed."

        target = "Its address" if rule.interface is None else rule.interface
        summary = f"{rule.device} — {target} must be inside {network}"

        candidates = (
            list(device.interfaces.values())
            if rule.interface is None
            else [item for item in [self._interface(device, rule.interface)] if item is not None]
        )
        addressed = [item for item in candidates if item.ip]
        if not addressed:
            return False, summary, f"{device.name} has no address configured there."

        for interface in addressed:
            if ipaddress.IPv4Address(interface.ip or "") in network:
                return True, summary, f"{interface.name} is {interface.ip}."

        found = ", ".join(f"{item.name} {item.ip}" for item in addressed)
        return False, summary, f"Found {found}, which is outside {network}."

    def _check_gateway(self, rule: GatewayRule) -> tuple[bool, str, str | None]:
        device = self._device(rule.device)
        if device is None:
            return self._missing(rule.device)

        summary = f"{rule.device} must use {rule.gateway} as its default gateway"
        actual = device.config.default_gateway
        if actual == rule.gateway:
            return True, summary, None
        return False, summary, f"Its gateway is {actual or 'not set'}."

    def _check_hostname(self, rule: HostnameRule) -> tuple[bool, str, str | None]:
        device = self._device(rule.device)
        if device is None:
            return self._missing(rule.device)

        summary = f"{rule.device} must have the hostname {rule.hostname}"
        actual = device.config.hostname
        # IOS hostnames are case-sensitive on screen but nobody fails a lab for
        # typing 'r1'; the prompt is what matters.
        if actual.strip().lower() == rule.hostname.strip().lower():
            return True, summary, None
        return False, summary, f"Its hostname is {actual or 'unset'}."

    def _check_static_route(self, rule: StaticRouteRule) -> tuple[bool, str, str | None]:
        device = self._device(rule.device)
        if device is None:
            return self._missing(rule.device)

        try:
            wanted = ipaddress.IPv4Network(rule.network, strict=False)
        except ValueError:
            return False, f"{rule.network} must be a valid subnet", "The lab's rule is malformed."

        via = f" via {rule.next_hop}" if rule.next_hop else ""
        summary = f"{rule.device} must have a static route to {wanted}{via}"

        for route in device.config.static_routes:
            try:
                configured = ipaddress.IPv4Network(f"{route.network}/{route.mask}", strict=False)
            except ValueError:
                continue
            if configured != wanted:
                continue
            if rule.next_hop and route.next_hop != rule.next_hop:
                return False, summary, f"The route points at {route.next_hop or 'no next hop'}."
            return True, summary, None

        if not device.config.static_routes:
            return False, summary, f"{device.name} has no static routes configured."
        configured_list = ", ".join(
            f"{item.network}/{item.mask}" for item in device.config.static_routes
        )
        return False, summary, f"Its routes are: {configured_list}."

    def _check_vlan(self, rule: VlanRule) -> tuple[bool, str, str | None]:
        device = self._device(rule.device)
        if device is None:
            return self._missing(rule.device)

        interface = self._interface(device, rule.interface)
        summary = f"{rule.device} {rule.interface} must be an access port in VLAN {rule.vlan}"
        if interface is None:
            return False, summary, f"{device.name} has no interface called {rule.interface}."
        if interface.switchport_mode != "access":
            mode = interface.switchport_mode or "not configured as a switchport"
            return False, summary, f"The port is {mode}."
        if interface.access_vlan != rule.vlan:
            return False, summary, f"It is in VLAN {interface.access_vlan}."
        return True, summary, None

    def _check_dhcp_pool(self, rule: DhcpPoolRule) -> tuple[bool, str, str | None]:
        device = self._device(rule.device)
        if device is None:
            return self._missing(rule.device)

        try:
            wanted = ipaddress.IPv4Network(rule.network, strict=False)
        except ValueError:
            return False, f"{rule.network} must be a valid subnet", "The lab's rule is malformed."

        summary = f"{rule.device} must serve DHCP for {wanted}"
        for pool in device.config.dhcp_pools:
            try:
                configured = ipaddress.IPv4Network(f"{pool.network}/{pool.mask}", strict=False)
            except ValueError:
                continue
            if configured == wanted:
                return True, summary, f"Pool '{pool.name}' covers {configured}."

        if not device.config.dhcp_pools:
            return False, summary, f"{device.name} has no DHCP pools configured."
        names = ", ".join(item.name for item in device.config.dhcp_pools)
        return False, summary, f"Its pools are: {names}."

    def _check_device_count(self, rule: DeviceCountRule) -> tuple[bool, str, str | None]:
        found = sum(1 for device in self.network.devices.values() if device.kind.value == rule.kind)
        label = rule.kind.replace("_", " ")
        bound = (
            f"at least {rule.minimum}"
            if rule.maximum is None
            else f"between {rule.minimum} and {rule.maximum}"
        )
        summary = f"The network must contain {bound} {label} device(s)"

        if found < rule.minimum:
            return False, summary, f"There are {found}."
        if rule.maximum is not None and found > rule.maximum:
            return False, summary, f"There are {found}, which is more than needed."
        return True, summary, f"Found {found}."

    def _check_link(self, rule: LinkRule) -> tuple[bool, str, str | None]:
        source = self._device(rule.source)
        destination = self._device(rule.destination)
        if source is None:
            return self._missing(rule.source)
        if destination is None:
            return self._missing(rule.destination)

        summary = f"{rule.source} must be cabled to {rule.destination}"
        ends = {source.id, destination.id}
        matching = [
            link for link in self.network.links.values() if {link.a_device, link.b_device} == ends
        ]
        if not matching:
            return False, summary, "There is no cable between them."

        # A cable that exists but cannot pass traffic is a different failure
        # from no cable at all, and the student needs to be told which it is.
        usable = next((link for link in matching if link.usable), None)
        if usable is not None:
            return True, summary, f"Connected with a {usable.cable.value.replace('_', ' ')} cable."

        broken = matching[0]
        if not broken.enabled:
            return False, summary, "The cable is there but the link is disabled."
        return (
            False,
            summary,
            f"The cable is a {broken.cable.value.replace('_', ' ')}, which is the wrong type here.",
        )
