"""Render a `DeviceConfig` back to Cisco IOS syntax.

This is what `show running-config` prints. It matters beyond display: it is the
proof that the forms and the CLI write to the same model. Configure an address
in a form, type `show run` at the CLI, and the line appears — because both are
reading this renderer over one document.

Part 8's lab grader will also match against this output, so the formatting
follows real IOS conventions: two-space indentation inside interface blocks,
`!` separators, and the same command ordering IOS itself emits.
"""

from __future__ import annotations

from app.models.enums import DeviceKind
from app.schemas.device_config import (
    DeviceConfig,
    InterfaceConfig,
    admin_up,
    mask_to_prefix,
    wildcard_to_mask,
)
from app.services.device_catalog import spec_for

SEPARATOR = "!"


def _traffic_interfaces(spec: object) -> list[str]:
    """Interface names excluding console ports."""
    return [
        str(entry["name"])
        for entry in spec.interfaces()  # type: ignore[attr-defined]
        if entry["connectable"]
    ]


def _interface_block(name: str, config: DeviceConfig, kind: DeviceKind) -> list[str]:
    # Unconfigured interfaces still appear, exactly as they do on real hardware
    # — an interface missing from `show run` would be a simulator artefact.
    interface = config.interfaces.get(name) or InterfaceConfig()

    lines = [f"interface {name}"]
    if interface.description:
        lines.append(f" description {interface.description}")

    # Switch-port settings come before addressing on a real device.
    if interface.switchport_mode == "access":
        lines.append(" switchport mode access")
        if interface.access_vlan:
            lines.append(f" switchport access vlan {interface.access_vlan}")
        if interface.voice_vlan:
            lines.append(f" switchport voice vlan {interface.voice_vlan}")
    elif interface.switchport_mode == "trunk":
        lines.append(" switchport mode trunk")
        if interface.native_vlan:
            lines.append(f" switchport trunk native vlan {interface.native_vlan}")
        if interface.allowed_vlans:
            allowed = ",".join(str(vlan) for vlan in sorted(interface.allowed_vlans))
            lines.append(f" switchport trunk allowed vlan {allowed}")

    if interface.dhcp:
        lines.append(" ip address dhcp")
    elif interface.ip_address and interface.subnet_mask:
        lines.append(f" ip address {interface.ip_address} {interface.subnet_mask}")
    else:
        # IOS prints this for an unaddressed interface, and its absence is a
        # common source of confusion when a link will not come up.
        lines.append(" no ip address")

    if interface.nat_side:
        lines.append(f" ip nat {interface.nat_side}")
    if interface.acl_in:
        lines.append(f" ip access-group {interface.acl_in} in")
    if interface.acl_out:
        lines.append(f" ip access-group {interface.acl_out} out")

    if interface.speed != "auto":
        lines.append(f" speed {interface.speed}")
    if interface.duplex != "auto":
        lines.append(f" duplex {interface.duplex}")

    # IOS prints `shutdown` for a disabled interface and nothing for an enabled
    # one — the absence of the line is what "up" looks like.
    if not admin_up(config.interfaces.get(name), kind.value):
        lines.append(" shutdown")

    return lines


def render_running_config(config: DeviceConfig, kind: DeviceKind) -> str:
    """Produce the device's running configuration."""
    spec = spec_for(kind)
    lines: list[str] = ["Building configuration...", "", "Current configuration:", SEPARATOR]

    hostname = config.hostname or spec.label.replace(" ", "")
    lines.append(f"hostname {hostname}")
    lines.append(SEPARATOR)

    if config.enable_secret:
        # Never echo the secret itself, exactly as IOS does not.
        lines.append("enable secret 5 $1$**********")
        lines.append(SEPARATOR)

    if config.banner_motd:
        lines.append(f"banner motd ^C{config.banner_motd}^C")
        lines.append(SEPARATOR)

    # VLAN database
    if config.vlans:
        for vlan in sorted(config.vlans, key=lambda item: item.id):
            lines.append(f"vlan {vlan.id}")
            if vlan.name:
                lines.append(f" name {vlan.name}")
        lines.append(SEPARATOR)

    # Interfaces in catalogue order rather than dictionary order, so output is
    # stable and matches how the device lists them. Console is excluded: it is
    # configured under `line con 0`, not as an interface.
    for name in _traffic_interfaces(spec):
        block = _interface_block(name, config, kind)
        if block:
            lines.extend(block)
            lines.append(SEPARATOR)

    # Routing protocols
    if config.ospf:
        lines.append(f"router ospf {config.ospf.process_id}")
        if config.ospf.router_id:
            lines.append(f" router-id {config.ospf.router_id}")
        for network in config.ospf.networks:
            lines.append(f" network {network.network} {network.wildcard} area {network.area}")
        for passive in config.ospf.passive_interfaces:
            lines.append(f" passive-interface {passive}")
        lines.append(SEPARATOR)

    if config.eigrp:
        lines.append(f"router eigrp {config.eigrp.as_number}")
        if config.eigrp.router_id:
            lines.append(f" eigrp router-id {config.eigrp.router_id}")
        for eigrp_network in config.eigrp.networks:
            suffix = f" {eigrp_network.wildcard}" if eigrp_network.wildcard else ""
            lines.append(f" network {eigrp_network.network}{suffix}")
        if not config.eigrp.auto_summary:
            lines.append(" no auto-summary")
        lines.append(SEPARATOR)

    if config.rip:
        lines.append("router rip")
        lines.append(f" version {config.rip.version}")
        for rip_network in config.rip.networks:
            lines.append(f" network {rip_network}")
        if not config.rip.auto_summary:
            lines.append(" no auto-summary")
        lines.append(SEPARATOR)

    # DHCP
    for pool in config.dhcp_pools:
        lines.append(f"ip dhcp pool {pool.name}")
        lines.append(f" network {pool.network} {pool.mask}")
        if pool.gateway:
            lines.append(f" default-router {pool.gateway}")
        if pool.dns_servers:
            lines.append(f" dns-server {' '.join(pool.dns_servers)}")
        if pool.domain_name:
            lines.append(f" domain-name {pool.domain_name}")
        lines.append(SEPARATOR)

    if config.dhcp_pools:
        for pool in config.dhcp_pools:
            if pool.excluded_start and pool.excluded_end:
                lines.append(f"ip dhcp excluded-address {pool.excluded_start} {pool.excluded_end}")
        lines.append(SEPARATOR)

    # Static routes
    for route in config.static_routes:
        target = route.next_hop or route.exit_interface or ""
        distance = f" {route.distance}" if route.distance != 1 else ""
        lines.append(f"ip route {route.network} {route.mask} {target}{distance}")
    if config.static_routes:
        lines.append(SEPARATOR)

    if config.default_gateway:
        lines.append(f"ip default-gateway {config.default_gateway}")
        lines.append(SEPARATOR)

    # Access lists
    for acl in config.acls:
        for rule in acl.entries:
            source = _address_clause(rule.source, rule.source_wildcard)
            if acl.kind == "standard":
                lines.append(f"access-list {acl.name} {rule.action} {source}")
            else:
                destination = _address_clause(rule.destination, rule.destination_wildcard)
                port = (
                    f" {rule.port_operator} {rule.destination_port}"
                    if rule.port_operator and rule.destination_port
                    else ""
                )
                lines.append(
                    f"access-list {acl.name} {rule.action} {rule.protocol} "
                    f"{source} {destination}{port}"
                )
    if config.acls:
        lines.append(SEPARATOR)

    # NAT
    for nat in config.nat_rules:
        if nat.kind == "static" and nat.inside_local and nat.inside_global:
            lines.append(f"ip nat inside source static {nat.inside_local} {nat.inside_global}")
        elif nat.kind == "overload" and nat.access_list and nat.interface:
            lines.append(
                f"ip nat inside source list {nat.access_list} interface {nat.interface} overload"
            )
        elif nat.kind == "dynamic" and nat.access_list and nat.pool_name:
            lines.append(f"ip nat inside source list {nat.access_list} pool {nat.pool_name}")
    if config.nat_rules:
        lines.append(SEPARATOR)

    if config.dns_servers:
        lines.append(f"ip name-server {' '.join(config.dns_servers)}")
        lines.append(SEPARATOR)

    if config.wireless:
        wireless = config.wireless
        lines.append(f"dot11 ssid {wireless.ssid}")
        lines.append(f" authentication {wireless.security}")
        if not wireless.broadcast_ssid:
            lines.append(" no guest-mode")
        lines.append(SEPARATOR)

    lines.append("end")
    return "\n".join(lines)


def _address_clause(address: str, wildcard: str | None) -> str:
    """Render an ACL address: `any`, `host x.x.x.x`, or `network wildcard`."""
    if address == "any":
        return "any"
    if wildcard in (None, "0.0.0.0"):
        return f"host {address}"
    return f"{address} {wildcard}"


def render_interface_brief(config: DeviceConfig, kind: DeviceKind) -> str:
    """`show ip interface brief` — the fastest way to see what is up."""
    spec = spec_for(kind)
    header = f"{'Interface':<24}{'IP-Address':<16}{'OK?':<5}{'Method':<8}{'Status':<22}{'Protocol'}"
    lines = [header]

    for name in _traffic_interfaces(spec):
        interface = config.interfaces.get(name)
        address = "unassigned"
        method = "unset"
        if interface:
            if interface.dhcp:
                address, method = "unassigned", "DHCP"
            elif interface.ip_address:
                address, method = interface.ip_address, "manual"

        enabled = admin_up(interface, kind.value)
        # An interface with no cable would show "down/down" on real hardware;
        # link state arrives with the Part 7 simulation, so until then an
        # enabled interface reports up.
        status = "up" if enabled else "administratively down"
        protocol = "up" if enabled else "down"

        lines.append(f"{name:<24}{address:<16}{'YES':<5}{method:<8}{status:<22}{protocol}")

    return "\n".join(lines)


def render_ip_route(config: DeviceConfig, kind: DeviceKind) -> str:
    """`show ip route` — connected networks plus configured statics."""
    lines = [
        "Codes: C - connected, S - static, O - OSPF, D - EIGRP, R - RIP",
        "       * - candidate default",
        "",
    ]

    connected = config.configured_networks(kind.value)
    if not connected and not config.static_routes:
        lines.append("Gateway of last resort is not set")
        lines.append("")
        return "\n".join(lines)

    default_route = next(
        (route for route in config.static_routes if route.network == "0.0.0.0"), None
    )
    if default_route:
        target = default_route.next_hop or default_route.exit_interface
        lines.append(f"Gateway of last resort is {target} to network 0.0.0.0")
    else:
        lines.append("Gateway of last resort is not set")
    lines.append("")

    for name, network in connected:
        lines.append(f"C    {network} is directly connected, {name}")

    for route in config.static_routes:
        prefix = mask_to_prefix(route.mask)
        target = route.next_hop or route.exit_interface
        marker = "S*" if route.network == "0.0.0.0" else "S "
        via = f"via {route.next_hop}" if route.next_hop else f"directly connected, {target}"
        lines.append(f"{marker}   {route.network}/{prefix} [{route.distance}/0] {via}")

    # Networks advertised by a routing protocol are shown as configured, not as
    # learned — adjacency and route exchange arrive with Part 7.
    if config.ospf:
        for entry in config.ospf.networks:
            mask = wildcard_to_mask(entry.wildcard)
            lines.append(
                f"O    {entry.network}/{mask_to_prefix(mask)} is advertised in area {entry.area}"
            )

    return "\n".join(lines)


def render_vlan_brief(config: DeviceConfig, kind: DeviceKind) -> str:
    """`show vlan brief` — VLANs and the access ports assigned to them."""
    lines = [
        f"{'VLAN':<6}{'Name':<34}{'Status':<11}Ports",
        f"{'----':<6}{'-' * 32:<34}{'---------':<11}{'-' * 30}",
    ]

    vlans = {vlan.id: vlan.name or f"VLAN{vlan.id:04d}" for vlan in config.vlans}
    # VLAN 1 always exists on a switch, whether or not anyone declared it.
    vlans.setdefault(1, "default")

    for vlan_id in sorted(vlans):
        ports = [
            _short_name(name, kind)
            for name, interface in config.interfaces.items()
            if interface.switchport_mode == "access" and (interface.access_vlan or 1) == vlan_id
        ]
        lines.append(f"{vlan_id:<6}{vlans[vlan_id]:<34}{'active':<11}{', '.join(sorted(ports))}")

    return "\n".join(lines)


def _short_name(interface: str, kind: DeviceKind) -> str:
    """`FastEthernet0/1` → `Fa0/1`, as IOS abbreviates in tabular output."""
    for entry in spec_for(kind).interfaces():
        if entry["name"] == interface:
            short = str(entry["shortName"])
            return short[:1].upper() + short[1:]
    return interface
