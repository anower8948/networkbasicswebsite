"""The device catalogue: what can be placed on the canvas and what ports it has.

This is the physical model the rest of the simulator rests on. Part 5 configures
these interfaces, Part 6's CLI addresses them by name, and Part 7 forwards
frames across the links between them — so the naming follows real Cisco
convention (`GigabitEthernet0/1`, `FastEthernet0/24`, `Serial0/0/0`) rather than
anything invented. A learner who types `interface g0/0` in Part 6 should be
talking about the same port they cabled here.

Port counts are modelled on real hardware: a 2960 has 24 FastEthernet access
ports plus two Gigabit uplinks, an ISR 2911 has three Gigabit interfaces and two
serial slots. Getting these right matters because lab exercises reference them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.models.enums import CableKind, DeviceKind, PortKind


@dataclass(frozen=True, slots=True)
class PortTemplate:
    """A range of identically-named ports, e.g. FastEthernet0/1 … 0/24."""

    prefix: str
    short_prefix: str
    kind: PortKind
    count: int
    # Most Cisco interfaces start at 1; router Gigabit ports start at 0.
    start: int = 1
    slot: str = "0/"

    def names(self) -> list[str]:
        return [
            f"{self.prefix}{self.slot}{index}"
            for index in range(self.start, self.start + self.count)
        ]

    def short_names(self) -> list[str]:
        return [
            f"{self.short_prefix}{self.slot}{index}"
            for index in range(self.start, self.start + self.count)
        ]


@dataclass(frozen=True, slots=True)
class DeviceSpec:
    """Everything the editor needs to place and cable one kind of device."""

    kind: DeviceKind
    label: str
    model: str
    description: str
    # Layer it primarily operates at, used for cable-type inference.
    osi_layer: int
    ports: list[PortTemplate] = field(default_factory=list)
    # Devices that can run the Part 6 CLI.
    has_cli: bool = False
    # Endpoints get an IP stack; infrastructure forwards for others.
    is_endpoint: bool = False

    def interface_names(self) -> list[str]:
        names: list[str] = []
        for template in self.ports:
            names.extend(template.names())
        return names

    def interfaces(self) -> list[dict[str, object]]:
        """Flattened interface list, as the editor and Part 5 consume it."""
        result: list[dict[str, object]] = []
        for template in self.ports:
            for full, short in zip(template.names(), template.short_names(), strict=True):
                result.append(
                    {
                        "name": full,
                        "shortName": short,
                        "kind": template.kind.value,
                        # Console ports carry no traffic, so they are never
                        # candidates for automatic link assignment.
                        "connectable": template.kind is not PortKind.CONSOLE,
                    }
                )
        return result


def _console() -> PortTemplate:
    return PortTemplate("Console", "con", PortKind.CONSOLE, count=1, start=0, slot="")


CATALOG: dict[DeviceKind, DeviceSpec] = {
    DeviceKind.PC: DeviceSpec(
        kind=DeviceKind.PC,
        label="PC",
        model="Generic desktop",
        description="An end-user workstation with a single network card.",
        osi_layer=7,
        is_endpoint=True,
        ports=[PortTemplate("Ethernet", "eth", PortKind.ETHERNET, count=1, start=0, slot="")],
    ),
    DeviceKind.LAPTOP: DeviceSpec(
        kind=DeviceKind.LAPTOP,
        label="Laptop",
        model="Generic laptop",
        description="A portable client with wired and wireless interfaces.",
        osi_layer=7,
        is_endpoint=True,
        ports=[
            PortTemplate("Ethernet", "eth", PortKind.ETHERNET, count=1, start=0, slot=""),
            PortTemplate("Wireless", "wlan", PortKind.WIRELESS, count=1, start=0, slot=""),
        ],
    ),
    DeviceKind.SERVER: DeviceSpec(
        kind=DeviceKind.SERVER,
        label="Server",
        model="Rack server",
        description="Hosts services such as DHCP, DNS, HTTP or file shares.",
        osi_layer=7,
        is_endpoint=True,
        ports=[PortTemplate("Ethernet", "eth", PortKind.ETHERNET, count=2, start=0, slot="")],
    ),
    DeviceKind.ROUTER: DeviceSpec(
        kind=DeviceKind.ROUTER,
        label="Router",
        model="ISR 2911",
        description="Routes between networks and enforces Layer 3 policy.",
        osi_layer=3,
        has_cli=True,
        ports=[
            # Router Gigabit interfaces start at 0/0, unlike switch ports.
            PortTemplate("GigabitEthernet", "g", PortKind.GIGABIT_ETHERNET, count=3, start=0),
            PortTemplate("Serial", "s", PortKind.SERIAL, count=2, start=0, slot="0/0/"),
            _console(),
        ],
    ),
    DeviceKind.SWITCH: DeviceSpec(
        kind=DeviceKind.SWITCH,
        label="Switch",
        model="Catalyst 2960",
        description="Forwards frames by MAC address within a broadcast domain.",
        osi_layer=2,
        has_cli=True,
        ports=[
            PortTemplate("FastEthernet", "fa", PortKind.FAST_ETHERNET, count=24),
            PortTemplate("GigabitEthernet", "g", PortKind.GIGABIT_ETHERNET, count=2),
            _console(),
        ],
    ),
    DeviceKind.MULTILAYER_SWITCH: DeviceSpec(
        kind=DeviceKind.MULTILAYER_SWITCH,
        label="Layer 3 switch",
        model="Catalyst 3560",
        description="Switches frames and routes between VLANs.",
        osi_layer=3,
        has_cli=True,
        ports=[
            PortTemplate("FastEthernet", "fa", PortKind.FAST_ETHERNET, count=24),
            PortTemplate("GigabitEthernet", "g", PortKind.GIGABIT_ETHERNET, count=4),
            _console(),
        ],
    ),
    DeviceKind.FIREWALL: DeviceSpec(
        kind=DeviceKind.FIREWALL,
        label="Firewall",
        model="ASA 5506-X",
        description="Filters traffic between security zones.",
        osi_layer=4,
        has_cli=True,
        ports=[
            PortTemplate("GigabitEthernet", "g", PortKind.GIGABIT_ETHERNET, count=4, start=0),
            _console(),
        ],
    ),
    DeviceKind.WIRELESS_ROUTER: DeviceSpec(
        kind=DeviceKind.WIRELESS_ROUTER,
        label="Wireless router",
        model="Home gateway",
        description="Combined router, switch and access point for small sites.",
        osi_layer=3,
        ports=[
            PortTemplate("Internet", "wan", PortKind.ETHERNET, count=1, start=0, slot=""),
            PortTemplate("LAN", "lan", PortKind.ETHERNET, count=4),
            PortTemplate("Wireless", "wlan", PortKind.WIRELESS, count=1, start=0, slot=""),
        ],
    ),
    DeviceKind.ACCESS_POINT: DeviceSpec(
        kind=DeviceKind.ACCESS_POINT,
        label="Access point",
        model="Aironet AP",
        description="Bridges wireless clients onto the wired network.",
        osi_layer=2,
        ports=[
            PortTemplate("GigabitEthernet", "g", PortKind.GIGABIT_ETHERNET, count=1, start=0),
            PortTemplate("Wireless", "wlan", PortKind.WIRELESS, count=1, start=0, slot=""),
        ],
    ),
    DeviceKind.CLOUD: DeviceSpec(
        kind=DeviceKind.CLOUD,
        label="Cloud",
        model="Public cloud",
        description="Represents a network beyond your control.",
        osi_layer=3,
        ports=[PortTemplate("Link", "link", PortKind.ETHERNET, count=4)],
    ),
    DeviceKind.ISP: DeviceSpec(
        kind=DeviceKind.ISP,
        label="ISP",
        model="Provider edge",
        description="Your upstream service provider.",
        osi_layer=3,
        ports=[
            PortTemplate("GigabitEthernet", "g", PortKind.GIGABIT_ETHERNET, count=2, start=0),
            PortTemplate("Serial", "s", PortKind.SERIAL, count=2, start=0, slot="0/0/"),
        ],
    ),
    DeviceKind.NAS: DeviceSpec(
        kind=DeviceKind.NAS,
        label="NAS",
        model="Network storage",
        description="Shared file storage on the local network.",
        osi_layer=7,
        is_endpoint=True,
        ports=[PortTemplate("Ethernet", "eth", PortKind.ETHERNET, count=2, start=0, slot="")],
    ),
    DeviceKind.PRINTER: DeviceSpec(
        kind=DeviceKind.PRINTER,
        label="Printer",
        model="Network printer",
        description="A shared printer with its own IP address.",
        osi_layer=7,
        is_endpoint=True,
        ports=[PortTemplate("Ethernet", "eth", PortKind.ETHERNET, count=1, start=0, slot="")],
    ),
    DeviceKind.CAMERA: DeviceSpec(
        kind=DeviceKind.CAMERA,
        label="IP camera",
        model="Surveillance camera",
        description="A PoE camera streaming to a recorder.",
        osi_layer=7,
        is_endpoint=True,
        ports=[PortTemplate("Ethernet", "eth", PortKind.ETHERNET, count=1, start=0, slot="")],
    ),
    DeviceKind.IP_PHONE: DeviceSpec(
        kind=DeviceKind.IP_PHONE,
        label="IP phone",
        model="Cisco 7900",
        description="A VoIP handset, usually on a dedicated voice VLAN.",
        osi_layer=7,
        is_endpoint=True,
        ports=[
            # Real handsets have a pass-through port for a daisy-chained PC.
            PortTemplate("Ethernet", "eth", PortKind.ETHERNET, count=1, start=0, slot=""),
            PortTemplate("PC-Port", "pc", PortKind.ETHERNET, count=1, start=0, slot=""),
        ],
    ),
    DeviceKind.IOT: DeviceSpec(
        kind=DeviceKind.IOT,
        label="IoT device",
        model="Smart sensor",
        description="A small connected device such as a sensor or smart plug.",
        osi_layer=7,
        is_endpoint=True,
        ports=[
            PortTemplate("Ethernet", "eth", PortKind.ETHERNET, count=1, start=0, slot=""),
            PortTemplate("Wireless", "wlan", PortKind.WIRELESS, count=1, start=0, slot=""),
        ],
    ),
}


def spec_for(kind: DeviceKind) -> DeviceSpec:
    return CATALOG[kind]


# --------------------------------------------------------------------------- #
# Cable selection
# --------------------------------------------------------------------------- #
# Devices whose Ethernet ports use the same pinout. Joining two devices from the
# same group needs a crossover; joining across groups needs a straight-through.
# This is the MDI/MDI-X rule CCNA candidates are examined on — modern gear
# auto-negotiates it, but the exam still asks, and so do the labs.
_MDI_DEVICES = frozenset(
    {
        DeviceKind.PC,
        DeviceKind.LAPTOP,
        DeviceKind.SERVER,
        DeviceKind.ROUTER,
        DeviceKind.FIREWALL,
        DeviceKind.NAS,
        DeviceKind.PRINTER,
        DeviceKind.CAMERA,
        DeviceKind.IP_PHONE,
        DeviceKind.IOT,
        DeviceKind.ISP,
    }
)
_MDIX_DEVICES = frozenset(
    {
        DeviceKind.SWITCH,
        DeviceKind.MULTILAYER_SWITCH,
        DeviceKind.ACCESS_POINT,
        DeviceKind.WIRELESS_ROUTER,
        DeviceKind.CLOUD,
    }
)


def _port_kind(kind: DeviceKind, interface: str) -> PortKind | None:
    for entry in spec_for(kind).interfaces():
        if entry["name"] == interface:
            return PortKind(str(entry["kind"]))
    return None


def recommended_cable(
    source_kind: DeviceKind,
    source_interface: str,
    target_kind: DeviceKind,
    target_interface: str,
) -> CableKind:
    """The cable a knowledgeable engineer would reach for.

    Port type wins over device type: two serial interfaces need a serial cable
    whatever the devices are, and any wireless interface implies no cable at all.
    """
    source_port = _port_kind(source_kind, source_interface)
    target_port = _port_kind(target_kind, target_interface)

    if PortKind.WIRELESS in (source_port, target_port):
        return CableKind.WIRELESS
    if PortKind.SERIAL in (source_port, target_port):
        return CableKind.SERIAL
    if PortKind.CONSOLE in (source_port, target_port):
        return CableKind.CONSOLE
    if PortKind.SFP in (source_port, target_port):
        return CableKind.FIBER

    same_pinout = (source_kind in _MDI_DEVICES and target_kind in _MDI_DEVICES) or (
        source_kind in _MDIX_DEVICES and target_kind in _MDIX_DEVICES
    )
    return CableKind.CROSSOVER if same_pinout else CableKind.STRAIGHT_THROUGH


def cable_warning(
    source_kind: DeviceKind,
    source_interface: str,
    target_kind: DeviceKind,
    target_interface: str,
    chosen: CableKind,
) -> str | None:
    """Explain why a chosen cable is wrong, or return None if it is fine.

    Returned as a **warning, not an error**: the point of a teaching simulator
    is to let a learner make the classic mistake and then understand it. Part 7
    will refuse to pass traffic over a miscabled link, which is exactly what
    happens in a real wiring closet.
    """
    expected = recommended_cable(source_kind, source_interface, target_kind, target_interface)
    if chosen is expected:
        return None

    source_port = _port_kind(source_kind, source_interface)
    target_port = _port_kind(target_kind, target_interface)

    if PortKind.SERIAL in (source_port, target_port) and chosen is not CableKind.SERIAL:
        return "Serial interfaces need a serial cable."
    if PortKind.WIRELESS in (source_port, target_port) and chosen is not CableKind.WIRELESS:
        return "Wireless interfaces are not cabled — use a wireless link."
    if chosen is CableKind.FIBER:
        return None  # fibre is acceptable anywhere the optics match

    if expected is CableKind.CROSSOVER:
        return (
            f"A {source_kind.value.replace('_', ' ')} and a "
            f"{target_kind.value.replace('_', ' ')} use the same pinout, so this link "
            "needs a crossover cable."
        )
    return (
        f"A {source_kind.value.replace('_', ' ')} and a "
        f"{target_kind.value.replace('_', ' ')} use opposite pinouts, so this link "
        "needs a straight-through cable."
    )


def catalog_payload() -> list[dict[str, object]]:
    """The whole catalogue, as the editor's device palette consumes it."""
    return [
        {
            "kind": spec.kind.value,
            "label": spec.label,
            "model": spec.model,
            "description": spec.description,
            "osiLayer": spec.osi_layer,
            "hasCli": spec.has_cli,
            "isEndpoint": spec.is_endpoint,
            "interfaces": spec.interfaces(),
        }
        for spec in CATALOG.values()
    ]
