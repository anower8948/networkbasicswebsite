"""The Cisco IOS command engine.

Executes one command line against a device's configuration and returns the
output, the new session state, and the updated configuration.

The engine **mutates the same `DeviceConfig` the configuration forms write to**.
That is the whole point of building Parts 5 and 6 together: `ip address
10.0.0.1 255.255.255.0` typed here and the same values entered in a form are
indistinguishable afterwards, and `show running-config` renders either.

Commands are dispatched by mode, then by an abbreviation-matched keyword, which
is how IOS itself is structured — `network` means something different inside
`router ospf` than it does inside `ip dhcp pool`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, cast

from app.models.enums import DeviceKind
from app.schemas.device_config import (
    AclConfig,
    AclEntry,
    DeviceConfig,
    DhcpPool,
    EigrpConfig,
    EigrpNetwork,
    NatRule,
    OspfConfig,
    OspfNetwork,
    RipConfig,
    StaticRoute,
    VlanConfig,
    validate_ipv4,
    validate_mask,
)
from app.services.cli.parsing import (
    ambiguous_command,
    expand_interface,
    incomplete_command,
    invalid_input,
    matches,
    parse_vlan_list,
    resolve,
    tokenize,
)
from app.services.cli.session import CliMode, CliSession
from app.services.device_catalog import spec_for

if TYPE_CHECKING:
    from app.services.simulation.network import Network

from app.services.running_config import (
    render_interface_brief,
    render_ip_route,
    render_running_config,
    render_vlan_brief,
)


@dataclass(slots=True)
class CommandResult:
    """What one command produced."""

    output: str
    session: CliSession
    config: DeviceConfig
    changed: bool = False


class CliEngine:
    """Executes IOS commands against one device."""

    def __init__(
        self,
        kind: DeviceKind,
        *,
        network: Network | None = None,
        device_id: str | None = None,
    ) -> None:
        self.kind = kind
        self.spec = spec_for(kind)
        # Supplied when the CLI runs inside a topology, which lets `ping`
        # actually forward a packet instead of reporting it cannot.
        self.network: Network | None = network
        self.device_id = device_id

    # ------------------------------------------------------------------ #
    # Entry point
    # ------------------------------------------------------------------ #
    def execute(self, line: str, session: CliSession, config: DeviceConfig) -> CommandResult:
        """Run one command line."""
        if not self.spec.has_cli:
            return CommandResult(
                f"% {self.spec.label} does not have a command-line interface.\n",
                session,
                config,
            )

        tokens = tokenize(line)
        if not tokens:
            return CommandResult("", session, config)

        # A leading `!` is a comment in IOS configuration files.
        if tokens[0].startswith("!"):
            return CommandResult("", session, config)

        # `no ...` negates; handled per-command so each knows its own inverse.
        negated = False
        if matches(tokens[0], "no") and len(tokens) > 1:
            negated = True
            tokens = tokens[1:]

        handlers = {
            CliMode.USER_EXEC: self._user_exec,
            CliMode.PRIV_EXEC: self._priv_exec,
            CliMode.GLOBAL_CONFIG: self._global_config,
            CliMode.INTERFACE_CONFIG: self._interface_config,
            CliMode.VLAN_CONFIG: self._vlan_config,
            CliMode.ROUTER_CONFIG: self._router_config,
            CliMode.LINE_CONFIG: self._line_config,
            CliMode.DHCP_CONFIG: self._dhcp_config,
        }
        return handlers[session.mode](tokens, negated, line, session, config)

    # ------------------------------------------------------------------ #
    # Mode handlers
    # ------------------------------------------------------------------ #
    def _user_exec(
        self, tokens: list[str], negated: bool, line: str, session: CliSession, config: DeviceConfig
    ) -> CommandResult:
        head = tokens[0]

        if matches(head, "enable"):
            return CommandResult("", session.model_copy(update={"mode": CliMode.PRIV_EXEC}), config)
        if matches(head, "exit") or matches(head, "logout"):
            return CommandResult("", session, config)
        if matches(head, "ping"):
            return self._ping(tokens, session, config)
        if matches(head, "show"):
            # User EXEC sees a reduced set on real gear; allowing the same
            # `show` commands keeps a learner from hitting an arbitrary wall.
            return self._show(tokens, line, session, config)
        if matches(head, "?"):
            return CommandResult(self._help_user_exec(), session, config)

        return CommandResult(invalid_input(line), session, config)

    def _priv_exec(
        self, tokens: list[str], negated: bool, line: str, session: CliSession, config: DeviceConfig
    ) -> CommandResult:
        head = tokens[0]

        if matches(head, "configure"):
            if len(tokens) < 2:
                return CommandResult(incomplete_command(), session, config)
            if not matches(tokens[1], "terminal"):
                return CommandResult(invalid_input(line, 1), session, config)
            return CommandResult(
                "Enter configuration commands, one per line.  End with CNTL/Z.\n",
                session.model_copy(update={"mode": CliMode.GLOBAL_CONFIG}),
                config,
            )

        if matches(head, "disable"):
            return CommandResult("", session.model_copy(update={"mode": CliMode.USER_EXEC}), config)
        if matches(head, "exit") or matches(head, "logout"):
            return CommandResult("", session.model_copy(update={"mode": CliMode.USER_EXEC}), config)
        if matches(head, "show"):
            return self._show(tokens, line, session, config)
        if matches(head, "ping"):
            return self._ping(tokens, session, config)
        if matches(head, "copy"):
            return self._copy(tokens, line, session, config)
        if matches(head, "write"):
            updated = config.model_copy(update={"saved": True})
            return CommandResult("Building configuration...\n[OK]\n", session, updated, True)
        if matches(head, "reload"):
            return CommandResult(
                "% Reload is simulated: unsaved configuration would be lost.\n"
                "% Device reloads arrive with the packet simulation engine.\n",
                session,
                config,
            )
        if matches(head, "clock") or matches(head, "terminal"):
            return CommandResult("", session, config)

        return CommandResult(invalid_input(line), session, config)

    def _global_config(
        self, tokens: list[str], negated: bool, line: str, session: CliSession, config: DeviceConfig
    ) -> CommandResult:
        head = tokens[0]
        updated = config.model_copy(deep=True)

        if matches(head, "exit"):
            return CommandResult("", session.leave(), config)
        if matches(head, "end"):
            return CommandResult("", session.to_privileged(), config)

        if matches(head, "hostname"):
            if len(tokens) < 2:
                return CommandResult(incomplete_command(), session, config)
            updated.hostname = tokens[1][:63]
            return CommandResult(
                "", session.model_copy(update={"hostname": updated.hostname}), updated, True
            )

        if matches(head, "interface"):
            if len(tokens) < 2:
                return CommandResult(incomplete_command(), session, config)
            name = expand_interface(tokens[1:], self.kind)
            if name is None:
                return CommandResult(invalid_input(line, 1), session, config)
            # Touch the interface so it exists in the config from now on.
            updated.interface(name)
            return CommandResult(
                "",
                session.model_copy(update={"mode": CliMode.INTERFACE_CONFIG, "interface": name}),
                updated,
                True,
            )

        if matches(head, "vlan"):
            return self._global_vlan(tokens, negated, line, session, updated)

        if matches(head, "ip"):
            return self._global_ip(tokens, negated, line, session, updated)

        if matches(head, "router"):
            return self._global_router(tokens, negated, line, session, updated)

        if matches(head, "access-list"):
            return self._access_list(tokens, negated, line, session, updated)

        if matches(head, "enable"):
            if len(tokens) < 3 or not (
                matches(tokens[1], "secret") or matches(tokens[1], "password")
            ):
                return CommandResult(incomplete_command(), session, config)
            updated.enable_secret = tokens[2]
            return CommandResult("", session, updated, True)

        if matches(head, "banner"):
            if len(tokens) < 3:
                return CommandResult(incomplete_command(), session, config)
            # IOS delimits the banner with a character of the operator's choice;
            # accept the rest of the line with the delimiters stripped.
            text = " ".join(tokens[2:]).strip()
            delimiter = text[:1]
            updated.banner_motd = text.strip(delimiter).strip()
            return CommandResult("", session, updated, True)

        if matches(head, "line"):
            if len(tokens) < 2:
                return CommandResult(incomplete_command(), session, config)
            return CommandResult(
                "",
                session.model_copy(
                    update={"mode": CliMode.LINE_CONFIG, "line": " ".join(tokens[1:])}
                ),
                config,
            )

        if matches(head, "service") or matches(head, "spanning-tree"):
            # Accepted and ignored: they parse on real gear, and rejecting them
            # would break a learner following a textbook transcript.
            return CommandResult("", session, config)

        return CommandResult(invalid_input(line), session, config)

    # ------------------------------------------------------------------ #
    # Global sub-commands
    # ------------------------------------------------------------------ #
    def _global_vlan(
        self, tokens: list[str], negated: bool, line: str, session: CliSession, config: DeviceConfig
    ) -> CommandResult:
        if len(tokens) < 2:
            return CommandResult(incomplete_command(), session, config)
        try:
            vlan_id = int(tokens[1])
        except ValueError:
            return CommandResult(invalid_input(line, 1), session, config)
        if not 1 <= vlan_id <= 4094:
            return CommandResult("% Invalid VLAN id (1-4094).\n", session, config)

        if negated:
            config.vlans = [vlan for vlan in config.vlans if vlan.id != vlan_id]
            return CommandResult("", session, config, True)

        if not any(vlan.id == vlan_id for vlan in config.vlans):
            config.vlans.append(VlanConfig(id=vlan_id))
        return CommandResult(
            "",
            session.model_copy(update={"mode": CliMode.VLAN_CONFIG, "vlan_id": vlan_id}),
            config,
            True,
        )

    def _global_ip(
        self, tokens: list[str], negated: bool, line: str, session: CliSession, config: DeviceConfig
    ) -> CommandResult:
        if len(tokens) < 2:
            return CommandResult(incomplete_command(), session, config)
        sub = tokens[1]

        # ip route <net> <mask> <next-hop|interface> [distance]
        if matches(sub, "route"):
            if len(tokens) < 5:
                return CommandResult(incomplete_command(), session, config)
            try:
                network = validate_ipv4(tokens[2])
                mask = validate_mask(tokens[3])
            except ValueError as exc:
                return CommandResult(f"% {exc}\n", session, config)

            target = tokens[4]
            distance = 1
            if len(tokens) >= 6:
                try:
                    distance = int(tokens[5])
                except ValueError:
                    return CommandResult(invalid_input(line, 5), session, config)

            if negated:
                config.static_routes = [
                    route
                    for route in config.static_routes
                    if not (route.network == network and route.mask == mask)
                ]
                return CommandResult("", session, config, True)

            try:
                # A dotted-quad target is a next hop; anything else is an
                # exit interface, exactly as IOS decides.
                next_hop = validate_ipv4(target)
                route = StaticRoute(
                    network=network, mask=mask, next_hop=next_hop, distance=distance
                )
            except ValueError:
                interface = expand_interface([target], self.kind)
                if interface is None:
                    return CommandResult(invalid_input(line, 4), session, config)
                route = StaticRoute(
                    network=network, mask=mask, exit_interface=interface, distance=distance
                )

            config.static_routes = [
                item
                for item in config.static_routes
                if not (item.network == network and item.mask == mask)
            ]
            config.static_routes.append(route)
            return CommandResult("", session, config, True)

        # ip default-gateway <address>
        if matches(sub, "default-gateway"):
            if negated:
                config.default_gateway = None
                return CommandResult("", session, config, True)
            if len(tokens) < 3:
                return CommandResult(incomplete_command(), session, config)
            try:
                config.default_gateway = validate_ipv4(tokens[2], "gateway")
            except ValueError as exc:
                return CommandResult(f"% {exc}\n", session, config)
            return CommandResult("", session, config, True)

        # ip name-server <address> [address...]
        if matches(sub, "name-server"):
            if negated:
                config.dns_servers = []
                return CommandResult("", session, config, True)
            if len(tokens) < 3:
                return CommandResult(incomplete_command(), session, config)
            try:
                config.dns_servers = [validate_ipv4(item, "DNS server") for item in tokens[2:]]
            except ValueError as exc:
                return CommandResult(f"% {exc}\n", session, config)
            return CommandResult("", session, config, True)

        # ip dhcp pool <name> | ip dhcp excluded-address <start> <end>
        if matches(sub, "dhcp"):
            if len(tokens) < 3:
                return CommandResult(incomplete_command(), session, config)
            if matches(tokens[2], "pool"):
                if len(tokens) < 4:
                    return CommandResult(incomplete_command(), session, config)
                name = tokens[3]
                if not any(pool.name == name for pool in config.dhcp_pools):
                    config.dhcp_pools.append(DhcpPool(name=name, network="0.0.0.0", mask="0.0.0.0"))
                return CommandResult(
                    "",
                    session.model_copy(update={"mode": CliMode.DHCP_CONFIG, "dhcp_pool": name}),
                    config,
                    True,
                )
            if matches(tokens[2], "excluded-address"):
                if len(tokens) < 5:
                    return CommandResult(incomplete_command(), session, config)
                if config.dhcp_pools:
                    try:
                        config.dhcp_pools[-1].excluded_start = validate_ipv4(tokens[3])
                        config.dhcp_pools[-1].excluded_end = validate_ipv4(tokens[4])
                    except ValueError as exc:
                        return CommandResult(f"% {exc}\n", session, config)
                return CommandResult("", session, config, True)
            return CommandResult(invalid_input(line, 2), session, config)

        # ip nat inside source ...
        if matches(sub, "nat"):
            return self._ip_nat(tokens, negated, line, session, config)

        return CommandResult(invalid_input(line, 1), session, config)

    def _ip_nat(
        self, tokens: list[str], negated: bool, line: str, session: CliSession, config: DeviceConfig
    ) -> CommandResult:
        # ip nat inside source static <local> <global>
        # ip nat inside source list <acl> interface <if> overload
        if len(tokens) < 5:
            return CommandResult(incomplete_command(), session, config)
        if not (matches(tokens[2], "inside") and matches(tokens[3], "source")):
            return CommandResult(invalid_input(line, 2), session, config)

        kind_token = tokens[4]

        if matches(kind_token, "static"):
            if len(tokens) < 7:
                return CommandResult(incomplete_command(), session, config)
            try:
                rule = NatRule(
                    kind="static",
                    inside_local=validate_ipv4(tokens[5]),
                    inside_global=validate_ipv4(tokens[6]),
                )
            except ValueError as exc:
                return CommandResult(f"% {exc}\n", session, config)
            config.nat_rules.append(rule)
            return CommandResult("", session, config, True)

        if matches(kind_token, "list"):
            if len(tokens) < 8:
                return CommandResult(incomplete_command(), session, config)
            acl = tokens[5]
            interface = expand_interface([tokens[7]], self.kind)
            if interface is None:
                return CommandResult(invalid_input(line, 7), session, config)
            overload = len(tokens) >= 9 and matches(tokens[8], "overload")
            config.nat_rules.append(
                NatRule(
                    kind="overload" if overload else "dynamic",
                    access_list=acl,
                    interface=interface,
                )
            )
            return CommandResult("", session, config, True)

        return CommandResult(invalid_input(line, 4), session, config)

    def _global_router(
        self, tokens: list[str], negated: bool, line: str, session: CliSession, config: DeviceConfig
    ) -> CommandResult:
        if len(tokens) < 2:
            return CommandResult(incomplete_command(), session, config)

        protocol, ambiguous = resolve(tokens[1], ["ospf", "eigrp", "rip"])
        if ambiguous:
            return CommandResult(ambiguous_command(tokens[1]), session, config)
        if protocol is None:
            return CommandResult(invalid_input(line, 1), session, config)

        process = 1
        if protocol in ("ospf", "eigrp"):
            if len(tokens) < 3:
                return CommandResult(incomplete_command(), session, config)
            try:
                process = int(tokens[2])
            except ValueError:
                return CommandResult(invalid_input(line, 2), session, config)

        if negated:
            setattr(config, protocol, None)
            return CommandResult("", session, config, True)

        if protocol == "ospf" and config.ospf is None:
            config.ospf = OspfConfig(process_id=process)
        elif protocol == "eigrp" and config.eigrp is None:
            config.eigrp = EigrpConfig(as_number=process)
        elif protocol == "rip" and config.rip is None:
            config.rip = RipConfig()

        return CommandResult(
            "",
            session.model_copy(
                update={
                    "mode": CliMode.ROUTER_CONFIG,
                    "router_protocol": protocol,
                    "router_process": process,
                }
            ),
            config,
            True,
        )

    def _access_list(
        self, tokens: list[str], negated: bool, line: str, session: CliSession, config: DeviceConfig
    ) -> CommandResult:
        # access-list <number> permit|deny ...
        if len(tokens) < 3:
            return CommandResult(incomplete_command(), session, config)
        name = tokens[1]

        if negated:
            config.acls = [acl for acl in config.acls if acl.name != name]
            return CommandResult("", session, config, True)

        action, ambiguous = resolve(tokens[2], ["permit", "deny"])
        if ambiguous or action is None:
            return CommandResult(invalid_input(line, 2), session, config)

        # 1-99 and 1300-1999 are standard; everything else here is extended.
        try:
            number = int(name)
            kind = "standard" if (1 <= number <= 99 or 1300 <= number <= 1999) else "extended"
        except ValueError:
            kind = "extended"

        acl = next((item for item in config.acls if item.name == name), None)
        if acl is None:
            acl = AclConfig(name=name, kind=cast(Literal["standard", "extended"], kind))
            config.acls.append(acl)

        rest = tokens[3:]
        try:
            entry = self._parse_acl_entry(action, kind, rest)
        except ValueError as exc:
            return CommandResult(f"% {exc}\n", session, config)

        entry.sequence = (len(acl.entries) + 1) * 10
        acl.entries.append(entry)
        return CommandResult("", session, config, True)

    @staticmethod
    def _parse_acl_entry(action: str, kind: str, rest: list[str]) -> AclEntry:
        """Parse the address part of an access-list statement."""
        if not rest:
            raise ValueError("Incomplete access-list statement.")

        def take_address(items: list[str]) -> tuple[str, str | None, list[str]]:
            head = items[0]
            if matches(head, "any"):
                return "any", None, items[1:]
            if matches(head, "host"):
                if len(items) < 2:
                    raise ValueError("Incomplete access-list statement.")
                return validate_ipv4(items[1]), "0.0.0.0", items[2:]
            if len(items) < 2:
                raise ValueError("Incomplete access-list statement.")
            return validate_ipv4(items[0]), validate_ipv4(items[1]), items[2:]

        if kind == "standard":
            source, wildcard, _ = take_address(rest)
            return AclEntry(
                action=cast(Literal["permit", "deny"], action),
                source=source,
                source_wildcard=wildcard,
            )

        protocol, _ = resolve(rest[0], ["ip", "tcp", "udp", "icmp"])
        if protocol is None:
            raise ValueError(f"Unknown protocol: {rest[0]}")
        source, source_wildcard, remainder = take_address(rest[1:])
        destination, destination_wildcard, remainder = take_address(remainder)

        operator = None
        port = None
        if remainder:
            operator_match, _ = resolve(remainder[0], ["eq", "gt", "lt", "neq"])
            if operator_match and len(remainder) >= 2:
                operator = operator_match
                # Well-known service names IOS accepts in place of a number.
                names = {
                    "www": 80,
                    "http": 80,
                    "https": 443,
                    "ftp": 21,
                    "ssh": 22,
                    "telnet": 23,
                    "smtp": 25,
                    "dns": 53,
                    "domain": 53,
                }
                token = remainder[1].lower()
                port = names.get(token, int(token) if token.isdigit() else None)

        return AclEntry(
            action=cast(Literal["permit", "deny"], action),
            protocol=cast(Literal["ip", "tcp", "udp", "icmp"], protocol),
            source=source,
            source_wildcard=source_wildcard,
            destination=destination,
            destination_wildcard=destination_wildcard,
            port_operator=cast(Literal["eq", "gt", "lt", "neq"] | None, operator),
            destination_port=port,
        )

    # ------------------------------------------------------------------ #
    # Interface configuration
    # ------------------------------------------------------------------ #
    def _interface_config(
        self, tokens: list[str], negated: bool, line: str, session: CliSession, config: DeviceConfig
    ) -> CommandResult:
        head = tokens[0]
        if matches(head, "exit"):
            return CommandResult("", session.leave(), config)
        if matches(head, "end"):
            return CommandResult("", session.to_privileged(), config)

        if session.interface is None:
            return CommandResult("% No interface selected.\n", session, config)

        updated = config.model_copy(deep=True)
        interface = updated.interface(session.interface)

        if matches(head, "shutdown"):
            interface.enabled = negated
            return CommandResult("", session, updated, True)

        if matches(head, "description"):
            if negated:
                interface.description = None
            else:
                if len(tokens) < 2:
                    return CommandResult(incomplete_command(), session, config)
                interface.description = " ".join(tokens[1:])[:200]
            return CommandResult("", session, updated, True)

        if matches(head, "ip"):
            if len(tokens) < 2:
                return CommandResult(incomplete_command(), session, config)
            sub = tokens[1]

            if matches(sub, "address"):
                if negated:
                    interface.ip_address = None
                    interface.subnet_mask = None
                    interface.dhcp = False
                    return CommandResult("", session, updated, True)
                if len(tokens) < 3:
                    return CommandResult(incomplete_command(), session, config)
                if matches(tokens[2], "dhcp"):
                    interface.dhcp = True
                    interface.ip_address = None
                    interface.subnet_mask = None
                    return CommandResult("", session, updated, True)
                if len(tokens) < 4:
                    return CommandResult(incomplete_command(), session, config)
                try:
                    address = validate_ipv4(tokens[2])
                    mask = validate_mask(tokens[3])
                except ValueError as exc:
                    return CommandResult(f"% {exc}\n", session, config)

                conflict = self._address_conflict(updated, session.interface, address, mask)
                if conflict:
                    # IOS refuses overlapping subnets on two interfaces, and the
                    # message names the interface already holding it.
                    return CommandResult(f"% {address} overlaps with {conflict}\n", session, config)

                interface.ip_address = address
                interface.subnet_mask = mask
                interface.dhcp = False
                return CommandResult("", session, updated, True)

            if matches(sub, "nat"):
                if len(tokens) < 3:
                    return CommandResult(incomplete_command(), session, config)
                side, _ = resolve(tokens[2], ["inside", "outside"])
                if side is None:
                    return CommandResult(invalid_input(line, 2), session, config)
                interface.nat_side = None if negated else cast(Literal["inside", "outside"], side)
                return CommandResult("", session, updated, True)

            if matches(sub, "access-group"):
                if len(tokens) < 4:
                    return CommandResult(incomplete_command(), session, config)
                direction, _ = resolve(tokens[3], ["in", "out"])
                if direction is None:
                    return CommandResult(invalid_input(line, 3), session, config)
                value = None if negated else tokens[2]
                if direction == "in":
                    interface.acl_in = value
                else:
                    interface.acl_out = value
                return CommandResult("", session, updated, True)

            return CommandResult(invalid_input(line, 1), session, config)

        if matches(head, "switchport"):
            return self._switchport(tokens, negated, line, session, updated, interface)

        if matches(head, "speed"):
            if len(tokens) < 2:
                return CommandResult(incomplete_command(), session, config)
            if tokens[1] not in ("auto", "10", "100", "1000"):
                return CommandResult(invalid_input(line, 1), session, config)
            interface.speed = cast(Literal["auto", "10", "100", "1000"], tokens[1])
            return CommandResult("", session, updated, True)

        if matches(head, "duplex"):
            if len(tokens) < 2:
                return CommandResult(incomplete_command(), session, config)
            value, _ = resolve(tokens[1], ["auto", "full", "half"])
            if value is None:
                return CommandResult(invalid_input(line, 1), session, config)
            interface.duplex = cast(Literal["auto", "full", "half"], value)
            return CommandResult("", session, updated, True)

        return CommandResult(invalid_input(line), session, config)

    @staticmethod
    def _address_conflict(
        config: DeviceConfig, current: str, address: str, mask: str
    ) -> str | None:
        """Find another interface already in the same subnet."""
        import ipaddress

        candidate = ipaddress.IPv4Interface(f"{address}/{mask}").network
        for name, interface in config.interfaces.items():
            if name == current:
                continue
            network = interface.network
            if network is not None and network.overlaps(candidate):
                return name
        return None

    def _switchport(
        self,
        tokens: list[str],
        negated: bool,
        line: str,
        session: CliSession,
        config: DeviceConfig,
        interface: object,
    ) -> CommandResult:
        from app.schemas.device_config import InterfaceConfig

        assert isinstance(interface, InterfaceConfig)

        if len(tokens) < 2:
            # Bare `switchport` enables Layer 2 mode on a capable port.
            interface.switchport_mode = interface.switchport_mode or "access"
            return CommandResult("", session, config, True)

        sub = tokens[1]

        if matches(sub, "mode"):
            if len(tokens) < 3:
                return CommandResult(incomplete_command(), session, config)
            mode, _ = resolve(tokens[2], ["access", "trunk"])
            if mode is None:
                return CommandResult(invalid_input(line, 2), session, config)
            interface.switchport_mode = cast(Literal["access", "trunk"], mode)
            return CommandResult("", session, config, True)

        if matches(sub, "access"):
            if len(tokens) < 4 or not matches(tokens[2], "vlan"):
                return CommandResult(incomplete_command(), session, config)
            try:
                vlan = int(tokens[3])
            except ValueError:
                return CommandResult(invalid_input(line, 3), session, config)
            if not 1 <= vlan <= 4094:
                return CommandResult("% Invalid VLAN id (1-4094).\n", session, config)
            interface.access_vlan = None if negated else vlan
            interface.switchport_mode = interface.switchport_mode or "access"
            return CommandResult("", session, config, True)

        if matches(sub, "voice"):
            if len(tokens) < 4:
                return CommandResult(incomplete_command(), session, config)
            try:
                interface.voice_vlan = None if negated else int(tokens[3])
            except ValueError:
                return CommandResult(invalid_input(line, 3), session, config)
            return CommandResult("", session, config, True)

        if matches(sub, "trunk"):
            if len(tokens) < 4:
                return CommandResult(incomplete_command(), session, config)
            if matches(tokens[2], "native"):
                try:
                    interface.native_vlan = int(tokens[4]) if len(tokens) > 4 else None
                except ValueError:
                    return CommandResult(invalid_input(line, 4), session, config)
                return CommandResult("", session, config, True)
            if matches(tokens[2], "allowed"):
                if len(tokens) < 5:
                    return CommandResult(incomplete_command(), session, config)
                try:
                    interface.allowed_vlans = parse_vlan_list(tokens[4])
                except ValueError as exc:
                    return CommandResult(f"% {exc}\n", session, config)
                return CommandResult("", session, config, True)

        return CommandResult(invalid_input(line, 1), session, config)

    # ------------------------------------------------------------------ #
    # Other configuration modes
    # ------------------------------------------------------------------ #
    def _vlan_config(
        self, tokens: list[str], negated: bool, line: str, session: CliSession, config: DeviceConfig
    ) -> CommandResult:
        head = tokens[0]
        if matches(head, "exit"):
            return CommandResult("", session.leave(), config)
        if matches(head, "end"):
            return CommandResult("", session.to_privileged(), config)

        if matches(head, "name"):
            if len(tokens) < 2:
                return CommandResult(incomplete_command(), session, config)
            updated = config.model_copy(deep=True)
            for vlan in updated.vlans:
                if vlan.id == session.vlan_id:
                    vlan.name = tokens[1][:64]
            return CommandResult("", session, updated, True)

        return CommandResult(invalid_input(line), session, config)

    def _router_config(
        self, tokens: list[str], negated: bool, line: str, session: CliSession, config: DeviceConfig
    ) -> CommandResult:
        head = tokens[0]
        if matches(head, "exit"):
            return CommandResult("", session.leave(), config)
        if matches(head, "end"):
            return CommandResult("", session.to_privileged(), config)

        updated = config.model_copy(deep=True)
        protocol = session.router_protocol

        if matches(head, "network"):
            if len(tokens) < 2:
                return CommandResult(incomplete_command(), session, config)
            try:
                network = validate_ipv4(tokens[1])
            except ValueError as exc:
                return CommandResult(f"% {exc}\n", session, config)

            if protocol == "ospf":
                # OSPF requires a wildcard and an area.
                if len(tokens) < 5 or not matches(tokens[3], "area"):
                    return CommandResult(incomplete_command(), session, config)
                try:
                    wildcard = validate_ipv4(tokens[2])
                    area = int(tokens[4])
                except ValueError:
                    return CommandResult(invalid_input(line, 2), session, config)
                if updated.ospf is None:
                    updated.ospf = OspfConfig(process_id=session.router_process or 1)
                updated.ospf.networks.append(
                    OspfNetwork(network=network, wildcard=wildcard, area=area)
                )
                return CommandResult("", session, updated, True)

            if protocol == "eigrp":
                # Named distinctly from the OSPF branch's `wildcard`, which
                # mypy binds as a non-optional str.
                eigrp_wildcard: str | None = None
                if len(tokens) >= 3:
                    try:
                        eigrp_wildcard = validate_ipv4(tokens[2])
                    except ValueError as exc:
                        return CommandResult(f"% {exc}\n", session, config)
                if updated.eigrp is None:
                    updated.eigrp = EigrpConfig(as_number=session.router_process or 1)
                updated.eigrp.networks.append(
                    EigrpNetwork(network=network, wildcard=eigrp_wildcard)
                )
                return CommandResult("", session, updated, True)

            if protocol == "rip":
                if updated.rip is None:
                    updated.rip = RipConfig()
                updated.rip.networks.append(network)
                return CommandResult("", session, updated, True)

        if matches(head, "router-id") and protocol == "ospf" and updated.ospf:
            if len(tokens) < 2:
                return CommandResult(incomplete_command(), session, config)
            try:
                updated.ospf.router_id = validate_ipv4(tokens[1], "router ID")
            except ValueError as exc:
                return CommandResult(f"% {exc}\n", session, config)
            return CommandResult("", session, updated, True)

        if matches(head, "passive-interface") and updated.ospf:
            if len(tokens) < 2:
                return CommandResult(incomplete_command(), session, config)
            name = expand_interface(tokens[1:], self.kind)
            if name is None:
                return CommandResult(invalid_input(line, 1), session, config)
            if negated:
                updated.ospf.passive_interfaces = [
                    item for item in updated.ospf.passive_interfaces if item != name
                ]
            else:
                updated.ospf.passive_interfaces.append(name)
            return CommandResult("", session, updated, True)

        if matches(head, "auto-summary"):
            if protocol == "eigrp" and updated.eigrp:
                updated.eigrp.auto_summary = not negated
            elif protocol == "rip" and updated.rip:
                updated.rip.auto_summary = not negated
            return CommandResult("", session, updated, True)

        if matches(head, "version") and protocol == "rip" and updated.rip:
            if len(tokens) < 2:
                return CommandResult(incomplete_command(), session, config)
            if tokens[1] not in ("1", "2"):
                return CommandResult(invalid_input(line, 1), session, config)
            updated.rip.version = cast(Literal[1, 2], int(tokens[1]))
            return CommandResult("", session, updated, True)

        return CommandResult(invalid_input(line), session, config)

    def _dhcp_config(
        self, tokens: list[str], negated: bool, line: str, session: CliSession, config: DeviceConfig
    ) -> CommandResult:
        head = tokens[0]
        if matches(head, "exit"):
            return CommandResult("", session.leave(), config)
        if matches(head, "end"):
            return CommandResult("", session.to_privileged(), config)

        updated = config.model_copy(deep=True)
        pool = next((item for item in updated.dhcp_pools if item.name == session.dhcp_pool), None)
        if pool is None:
            return CommandResult("% No DHCP pool selected.\n", session, config)

        try:
            if matches(head, "network"):
                if len(tokens) < 3:
                    return CommandResult(incomplete_command(), session, config)
                pool.network = validate_ipv4(tokens[1])
                pool.mask = validate_mask(tokens[2])
            elif matches(head, "default-router"):
                if len(tokens) < 2:
                    return CommandResult(incomplete_command(), session, config)
                pool.gateway = validate_ipv4(tokens[1], "gateway")
            elif matches(head, "dns-server"):
                if len(tokens) < 2:
                    return CommandResult(incomplete_command(), session, config)
                pool.dns_servers = [validate_ipv4(item, "DNS server") for item in tokens[1:]]
            elif matches(head, "domain-name"):
                if len(tokens) < 2:
                    return CommandResult(incomplete_command(), session, config)
                pool.domain_name = tokens[1][:128]
            else:
                return CommandResult(invalid_input(line), session, config)
        except ValueError as exc:
            return CommandResult(f"% {exc}\n", session, config)

        return CommandResult("", session, updated, True)

    def _line_config(
        self, tokens: list[str], negated: bool, line: str, session: CliSession, config: DeviceConfig
    ) -> CommandResult:
        head = tokens[0]
        if matches(head, "exit"):
            return CommandResult("", session.leave(), config)
        if matches(head, "end"):
            return CommandResult("", session.to_privileged(), config)
        # Line settings (password, login, logging synchronous) parse and are
        # accepted; none of them affect the simulation.
        return CommandResult("", session, config)

    # ------------------------------------------------------------------ #
    # show
    # ------------------------------------------------------------------ #
    def _show(
        self, tokens: list[str], line: str, session: CliSession, config: DeviceConfig
    ) -> CommandResult:
        if len(tokens) < 2:
            return CommandResult(incomplete_command(), session, config)

        sub = tokens[1]

        if matches(sub, "running-config"):
            return CommandResult(render_running_config(config, self.kind) + "\n", session, config)

        if matches(sub, "startup-config"):
            if not config.saved:
                return CommandResult("startup-config is not present\n", session, config)
            return CommandResult(render_running_config(config, self.kind) + "\n", session, config)

        if matches(sub, "version"):
            return CommandResult(self._version_text(config), session, config)

        if matches(sub, "vlan"):
            return CommandResult(render_vlan_brief(config, self.kind) + "\n", session, config)

        if matches(sub, "interfaces"):
            return CommandResult(render_interface_brief(config, self.kind) + "\n", session, config)

        if matches(sub, "ip"):
            if len(tokens) < 3:
                return CommandResult(incomplete_command(), session, config)
            third = tokens[2]

            if matches(third, "interface"):
                # `show ip interface brief` is the canonical form.
                if len(tokens) >= 4 and matches(tokens[3], "brief"):
                    return CommandResult(
                        render_interface_brief(config, self.kind) + "\n", session, config
                    )
                return CommandResult(
                    render_interface_brief(config, self.kind) + "\n", session, config
                )
            if matches(third, "route"):
                return CommandResult(render_ip_route(config, self.kind) + "\n", session, config)
            if matches(third, "nat"):
                return CommandResult(self._nat_translations(config), session, config)
            return CommandResult(invalid_input(line, 2), session, config)

        if matches(sub, "access-lists"):
            return CommandResult(self._show_access_lists(config), session, config)

        if matches(sub, "mac"):
            return CommandResult(
                "          Mac Address Table\n"
                "-------------------------------------------\n\n"
                "% The MAC address table is populated by traffic, which arrives\n"
                "% with the packet simulation engine.\n",
                session,
                config,
            )

        return CommandResult(invalid_input(line, 1), session, config)

    def _version_text(self, config: DeviceConfig) -> str:
        hostname = config.hostname or self.spec.label.replace(" ", "")
        return (
            "Cisco IOS Software, Simulated Software "
            f"({self.spec.model}), Version 15.2(4)E\n"
            "Network Learning Platform simulation — not a real device.\n\n"
            f"{hostname} uptime is 0 minutes\n"
            f'System image file is "flash:{self.spec.model.lower().replace(" ", "-")}.bin"\n\n'
            f"{self.spec.model} with 512K/16K bytes of memory.\n"
            f"{len([i for i in self.spec.interfaces() if i['connectable']])} "
            "network interfaces\n"
            f"Configuration register is 0x2102\n"
        )

    @staticmethod
    def _show_access_lists(config: DeviceConfig) -> str:
        if not config.acls:
            return ""
        lines: list[str] = []
        for acl in config.acls:
            label = "Standard" if acl.kind == "standard" else "Extended"
            lines.append(f"{label} IP access list {acl.name}")
            for entry in acl.entries:
                source = entry.source if entry.source == "any" else f"host {entry.source}"
                lines.append(f"    {entry.sequence} {entry.action} {source}")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _nat_translations(config: DeviceConfig) -> str:
        if not config.nat_rules:
            return "% No NAT rules configured.\n"
        lines = ["Pro  Inside global      Inside local       Outside local      Outside global"]
        for rule in config.nat_rules:
            if rule.kind == "static" and rule.inside_global and rule.inside_local:
                lines.append(
                    f"---  {rule.inside_global:<19}{rule.inside_local:<19}{'---':<19}{'---'}"
                )
        lines.append("")
        lines.append("% Live translations appear once traffic flows (Part 7).")
        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------ #
    # Misc
    # ------------------------------------------------------------------ #
    @staticmethod
    def _copy(
        tokens: list[str], line: str, session: CliSession, config: DeviceConfig
    ) -> CommandResult:
        if len(tokens) < 3:
            return CommandResult(incomplete_command(), session, config)
        if matches(tokens[1], "running-config") and matches(tokens[2], "startup-config"):
            updated = config.model_copy(update={"saved": True})
            return CommandResult(
                "Destination filename [startup-config]?\nBuilding configuration...\n[OK]\n",
                session,
                updated,
                True,
            )
        return CommandResult(invalid_input(line, 1), session, config)

    def _ping(self, tokens: list[str], session: CliSession, config: DeviceConfig) -> CommandResult:
        """Run a real ping when the CLI knows its topology.

        Without a topology (an engine constructed for tests, say) it says so
        rather than faking success — a simulator that claims a ping worked when
        nothing was forwarded teaches exactly the wrong thing.
        """
        if len(tokens) < 2:
            return CommandResult(incomplete_command(), session, config)
        target = tokens[1]

        if self.network is None or self.device_id is None:
            return CommandResult(
                "Type escape sequence to abort.\n"
                f"Sending 5, 100-byte ICMP Echos to {target}, timeout is 2 seconds:\n"
                "% This device is not attached to a simulated topology.\n",
                session,
                config,
            )

        from app.services.simulation.protocols import Simulator

        result = Simulator(self.network).ping(self.device_id, target, count=5)

        lines = [
            "Type escape sequence to abort.",
            f"Sending 5, 100-byte ICMP Echos to {target}, timeout is 2 seconds:",
        ]
        if result.success:
            # IOS prints one character per echo, then the success rate.
            lines.append("!!!!!")
            lines.append("Success rate is 100 percent (5/5), round-trip min/avg/max = 1/2/4 ms")
        else:
            lines.append(".....")
            lines.append("Success rate is 0 percent (0/5)")
            if result.failure_reason:
                lines.append(f"% {result.failure_reason}")
            if result.hint:
                lines.append(f"% {result.hint}")

        return CommandResult("\n".join(lines) + "\n", session, config)

    @staticmethod
    def _help_user_exec() -> str:
        return (
            "Exec commands:\n"
            "  enable    Turn on privileged commands\n"
            "  exit      Exit from the EXEC\n"
            "  ping      Send echo messages\n"
            "  show      Show running system information\n"
        )
