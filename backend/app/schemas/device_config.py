"""Device configuration.

This is the model that fills `TopologyDevice.config`, left deliberately untyped
in Part 4. Two editors write to it and must never disagree:

* the configuration windows (Part 5), and
* the Cisco CLI (Part 6).

Because there is exactly one model, `ip address 10.0.0.1 255.255.255.0` typed at
the CLI and the same values entered in a form produce an identical document —
and `show running-config` renders that document back to IOS syntax whichever way
it was set.

Validation is real: addresses must parse, masks must be contiguous, VLAN ids
must be in range. A learner who types an impossible mask should be told, the way
IOS would tell them.
"""

from __future__ import annotations

import ipaddress
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

MAX_VLAN_ID = 4094


class ConfigModel(BaseModel):
    """Base for every configuration model.

    camelCase on the wire, matching the rest of the API and the stored topology
    document; snake_case still accepted on input. `extra="forbid"` because
    configuration round-trips verbatim — an unrecognised key is a bug, not
    something to silently drop on the next save.
    """

    model_config = ConfigDict(
        extra="forbid",
        alias_generator=to_camel,
        populate_by_name=True,
    )


# --------------------------------------------------------------------------- #
# Shared validators
# --------------------------------------------------------------------------- #
def validate_ipv4(value: str, field: str = "address") -> str:
    try:
        return str(ipaddress.IPv4Address(value.strip()))
    except ipaddress.AddressValueError as exc:
        raise ValueError(f"'{value}' is not a valid IPv4 {field}.") from exc


def validate_mask(value: str) -> str:
    """Accept a dotted-decimal mask, rejecting non-contiguous ones.

    255.255.0.255 parses as an address but is not a legal mask — the 1 bits must
    be contiguous from the left. Real IOS rejects it, and a learner who typed it
    has a genuine misconception worth surfacing.
    """
    try:
        address = ipaddress.IPv4Address(value.strip())
    except ipaddress.AddressValueError as exc:
        raise ValueError(f"'{value}' is not a valid subnet mask.") from exc

    bits = int(address)
    # A contiguous mask inverted-plus-one is a power of two.
    inverted = ~bits & 0xFFFFFFFF
    if inverted & (inverted + 1) != 0:
        raise ValueError(f"'{value}' is not a contiguous subnet mask.")
    return str(address)


# Device families whose ports come up without configuration.
_PORTS_UP_BY_DEFAULT = frozenset({"switch", "multilayer_switch", "access_point", "cloud"})


def admin_up(interface: InterfaceConfig | None, device_kind: str) -> bool:
    """Resolve an interface's administrative state for a device kind."""
    if interface is not None and interface.enabled is not None:
        return interface.enabled
    return device_kind in _PORTS_UP_BY_DEFAULT


def mask_to_prefix(mask: str) -> int:
    return bin(int(ipaddress.IPv4Address(mask))).count("1")


def prefix_to_mask(prefix: int) -> str:
    return str(ipaddress.IPv4Network(f"0.0.0.0/{prefix}").netmask)


def wildcard_to_mask(wildcard: str) -> str:
    """OSPF and ACLs take wildcard masks — the bitwise inverse of a netmask."""
    inverted = ~int(ipaddress.IPv4Address(wildcard)) & 0xFFFFFFFF
    return str(ipaddress.IPv4Address(inverted))


# --------------------------------------------------------------------------- #
# Interfaces
# --------------------------------------------------------------------------- #
SwitchportMode = Literal["access", "trunk"]
DuplexSetting = Literal["auto", "full", "half"]
SpeedSetting = Literal["auto", "10", "100", "1000"]


class InterfaceConfig(ConfigModel):
    """One interface's configuration."""

    description: str | None = Field(default=None, max_length=200)

    # Layer 3
    ip_address: str | None = None
    subnet_mask: str | None = None
    # DHCP client, as `ip address dhcp` on IOS.
    dhcp: bool = False

    # Tri-state on purpose. `None` means "never configured", which resolves to
    # the *device's* default — and those differ: a Catalyst switch's ports are
    # up out of the box, while a router's interfaces are administratively down
    # until `no shutdown`. That asymmetry is examinable CCNA material, and
    # collapsing it to a single boolean would model one of them wrongly.
    # `shutdown` sets False and `no shutdown` sets True, either of which wins.
    enabled: bool | None = None

    speed: SpeedSetting = "auto"
    duplex: DuplexSetting = "auto"

    # Layer 2 (switch ports)
    switchport_mode: SwitchportMode | None = None
    access_vlan: int | None = Field(default=None, ge=1, le=MAX_VLAN_ID)
    voice_vlan: int | None = Field(default=None, ge=1, le=MAX_VLAN_ID)
    native_vlan: int | None = Field(default=None, ge=1, le=MAX_VLAN_ID)
    allowed_vlans: list[int] = Field(default_factory=list)

    # Policy
    nat_side: Literal["inside", "outside"] | None = None
    acl_in: str | None = Field(default=None, max_length=64)
    acl_out: str | None = Field(default=None, max_length=64)

    @field_validator("ip_address")
    @classmethod
    def _check_ip(cls, value: str | None) -> str | None:
        return validate_ipv4(value) if value else None

    @field_validator("subnet_mask")
    @classmethod
    def _check_mask(cls, value: str | None) -> str | None:
        return validate_mask(value) if value else None

    @model_validator(mode="after")
    def _address_needs_mask(self) -> InterfaceConfig:
        if self.ip_address and not self.subnet_mask:
            raise ValueError("An IP address requires a subnet mask.")
        return self

    @property
    def prefix_length(self) -> int | None:
        return mask_to_prefix(self.subnet_mask) if self.subnet_mask else None

    @property
    def network(self) -> ipaddress.IPv4Network | None:
        """The subnet this interface sits in."""
        if not (self.ip_address and self.subnet_mask):
            return None
        return ipaddress.IPv4Interface(f"{self.ip_address}/{self.subnet_mask}").network


# --------------------------------------------------------------------------- #
# Layer 2
# --------------------------------------------------------------------------- #
class VlanConfig(ConfigModel):
    id: int = Field(ge=1, le=MAX_VLAN_ID)
    name: str = Field(default="", max_length=64)


# --------------------------------------------------------------------------- #
# Layer 3
# --------------------------------------------------------------------------- #
class StaticRoute(ConfigModel):
    network: str
    mask: str
    next_hop: str | None = None
    exit_interface: str | None = Field(default=None, max_length=64)
    distance: int = Field(default=1, ge=1, le=255)

    @field_validator("network", "next_hop")
    @classmethod
    def _check_ip(cls, value: str | None) -> str | None:
        return validate_ipv4(value) if value else None

    @field_validator("mask")
    @classmethod
    def _check_mask(cls, value: str) -> str:
        return validate_mask(value)

    @model_validator(mode="after")
    def _needs_a_destination(self) -> StaticRoute:
        if not self.next_hop and not self.exit_interface:
            raise ValueError("A static route needs a next hop or an exit interface.")
        return self


class OspfNetwork(ConfigModel):
    network: str
    wildcard: str
    area: int = Field(default=0, ge=0, le=4294967295)

    @field_validator("network", "wildcard")
    @classmethod
    def _check_ip(cls, value: str) -> str:
        return validate_ipv4(value)


class OspfConfig(ConfigModel):
    process_id: int = Field(default=1, ge=1, le=65535)
    router_id: str | None = None
    networks: list[OspfNetwork] = Field(default_factory=list)
    passive_interfaces: list[str] = Field(default_factory=list)

    @field_validator("router_id")
    @classmethod
    def _check_router_id(cls, value: str | None) -> str | None:
        return validate_ipv4(value, "router ID") if value else None


class EigrpNetwork(ConfigModel):
    network: str
    wildcard: str | None = None

    @field_validator("network")
    @classmethod
    def _check_network(cls, value: str) -> str:
        return validate_ipv4(value)

    @field_validator("wildcard")
    @classmethod
    def _check_wildcard(cls, value: str | None) -> str | None:
        return validate_ipv4(value) if value else None


class EigrpConfig(ConfigModel):
    as_number: int = Field(default=1, ge=1, le=65535)
    router_id: str | None = None
    networks: list[EigrpNetwork] = Field(default_factory=list)
    # EIGRP and RIP auto-summarise by default; CCNA labs almost always disable it.
    auto_summary: bool = False


class RipConfig(ConfigModel):
    version: Literal[1, 2] = 2
    networks: list[str] = Field(default_factory=list)
    auto_summary: bool = False

    @field_validator("networks")
    @classmethod
    def _check_networks(cls, value: list[str]) -> list[str]:
        return [validate_ipv4(item) for item in value]


# --------------------------------------------------------------------------- #
# Services and policy
# --------------------------------------------------------------------------- #
class DhcpPool(ConfigModel):
    name: str = Field(min_length=1, max_length=64)
    network: str
    mask: str
    gateway: str | None = None
    dns_servers: list[str] = Field(default_factory=list)
    domain_name: str | None = Field(default=None, max_length=128)
    lease_hours: int = Field(default=24, ge=1, le=8760)
    excluded_start: str | None = None
    excluded_end: str | None = None

    @field_validator("network", "gateway", "excluded_start", "excluded_end")
    @classmethod
    def _check_ip(cls, value: str | None) -> str | None:
        return validate_ipv4(value) if value else None

    @field_validator("mask")
    @classmethod
    def _check_mask(cls, value: str) -> str:
        return validate_mask(value)

    @field_validator("dns_servers")
    @classmethod
    def _check_dns(cls, value: list[str]) -> list[str]:
        return [validate_ipv4(item) for item in value]


class AclEntry(ConfigModel):
    sequence: int = Field(default=10, ge=1, le=2147483647)
    action: Literal["permit", "deny"]
    protocol: Literal["ip", "tcp", "udp", "icmp"] = "ip"
    source: str = "any"
    source_wildcard: str | None = None
    destination: str = "any"
    destination_wildcard: str | None = None
    destination_port: int | None = Field(default=None, ge=1, le=65535)
    port_operator: Literal["eq", "gt", "lt", "neq"] | None = None


class AclConfig(ConfigModel):
    """A numbered or named access list.

    Numbers 1–99 and 1300–1999 are standard (source only); 100–199 and 2000–2699
    are extended. The distinction matters because a standard ACL cannot match a
    destination, which is a classic exam point.
    """

    name: str = Field(min_length=1, max_length=64)
    kind: Literal["standard", "extended"] = "standard"
    entries: list[AclEntry] = Field(default_factory=list)


class NatRule(ConfigModel):
    kind: Literal["static", "dynamic", "overload"] = "overload"
    inside_local: str | None = None
    inside_global: str | None = None
    access_list: str | None = Field(default=None, max_length=64)
    pool_name: str | None = Field(default=None, max_length=64)
    interface: str | None = Field(default=None, max_length=64)

    @field_validator("inside_local", "inside_global")
    @classmethod
    def _check_ip(cls, value: str | None) -> str | None:
        return validate_ipv4(value) if value else None


class WirelessConfig(ConfigModel):
    ssid: str = Field(default="", max_length=32)
    security: Literal["open", "wep", "wpa2-psk", "wpa3-psk"] = "wpa2-psk"
    passphrase: str = Field(default="", max_length=63)
    channel: int = Field(default=6, ge=1, le=165)
    band: Literal["2.4", "5"] = "2.4"
    broadcast_ssid: bool = True


# --------------------------------------------------------------------------- #
# The whole device
# --------------------------------------------------------------------------- #
class DeviceConfig(ConfigModel):
    """Everything configurable on one device.

    A single model covers routers, switches and PCs rather than one per kind:
    the CLI and the forms both need to read a device's configuration without
    branching on its type, and a multilayer switch genuinely has both switch and
    router features.
    """

    hostname: str = Field(default="", max_length=63)
    enable_secret: str | None = Field(default=None, max_length=64)
    banner_motd: str | None = Field(default=None, max_length=500)

    interfaces: dict[str, InterfaceConfig] = Field(default_factory=dict)

    # Endpoints and Layer 2 switches have one gateway, not a routing table.
    default_gateway: str | None = None
    dns_servers: list[str] = Field(default_factory=list)
    # `ip address dhcp` on the endpoint's only interface.
    dhcp_client: bool = False

    vlans: list[VlanConfig] = Field(default_factory=list)
    static_routes: list[StaticRoute] = Field(default_factory=list)
    ospf: OspfConfig | None = None
    eigrp: EigrpConfig | None = None
    rip: RipConfig | None = None
    dhcp_pools: list[DhcpPool] = Field(default_factory=list)
    acls: list[AclConfig] = Field(default_factory=list)
    nat_rules: list[NatRule] = Field(default_factory=list)
    wireless: WirelessConfig | None = None

    # Set by `copy running-config startup-config`. Part 7 will reset unsaved
    # configuration on a simulated reload, which is a lesson in itself.
    saved: bool = False

    @field_validator("default_gateway")
    @classmethod
    def _check_gateway(cls, value: str | None) -> str | None:
        return validate_ipv4(value, "gateway") if value else None

    @field_validator("dns_servers")
    @classmethod
    def _check_dns(cls, value: list[str]) -> list[str]:
        return [validate_ipv4(item, "DNS server") for item in value]

    def interface(self, name: str) -> InterfaceConfig:
        """Get an interface's configuration, creating a default if unset."""
        return self.interfaces.setdefault(name, InterfaceConfig())

    def configured_networks(
        self, device_kind: str = "router"
    ) -> list[tuple[str, ipaddress.IPv4Network]]:
        """Every directly connected network, for route tables and validation."""
        result: list[tuple[str, ipaddress.IPv4Network]] = []
        for name, interface in self.interfaces.items():
            network = interface.network
            if network is not None and admin_up(interface, device_kind):
                result.append((name, network))
        return result
