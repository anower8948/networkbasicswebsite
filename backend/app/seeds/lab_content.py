"""Seeded hands-on labs.

Four labs, one per `LabKind`, chosen so that each demonstrates a different part
of the grading model rather than four variations on "make a ping work":

* **guided** — build a flat LAN from scratch; graded on addressing *and* on
  traffic actually flowing.
* **challenge** — route between two subnets; graded on the gateway decision,
  which is the concept most beginners get wrong.
* **troubleshooting** — a working network broken by injected faults; the
  student never sees the fault list.
* **design** — VLAN segmentation, graded partly on what must **not** be
  reachable. Without that assertion a student could pass by cabling everything
  together.

For build labs the `initial_topology` is where the student *starts* — cabled but
unconfigured — so it deliberately scores zero against its own rules.

A **troubleshooting** lab is the other way round: its `initial_topology` is the
finished, working network, and the faults break it when an attempt begins. That
order matters, because it lets an author prove the network passes its own rules
before deciding how to break it. `tests/test_labs.py` asserts exactly that.
"""

from __future__ import annotations

from typing import Any


def _pc(
    device_id: str,
    name: str,
    x: int,
    y: int,
    *,
    ip: str | None = None,
    gateway: str | None = None,
) -> dict[str, Any]:
    config: dict[str, Any] = {}
    if ip:
        config["interfaces"] = {
            "Ethernet0": {"ipAddress": ip, "subnetMask": "255.255.255.0", "enabled": True}
        }
    if gateway:
        config["defaultGateway"] = gateway
    return {
        "id": device_id,
        "kind": "pc",
        "name": name,
        "position": {"x": x, "y": y},
        "config": config,
    }


def _server(
    device_id: str, name: str, x: int, y: int, *, ip: str, gateway: str | None = None
) -> dict[str, Any]:
    config: dict[str, Any] = {
        "interfaces": {
            "Ethernet0": {"ipAddress": ip, "subnetMask": "255.255.255.0", "enabled": True}
        }
    }
    if gateway:
        config["defaultGateway"] = gateway
    return {
        "id": device_id,
        "kind": "server",
        "name": name,
        "position": {"x": x, "y": y},
        "config": config,
    }


def _switch(device_id: str, name: str, x: int, y: int, **config: Any) -> dict[str, Any]:
    return {
        "id": device_id,
        "kind": "switch",
        "name": name,
        "position": {"x": x, "y": y},
        "config": {"hostname": name, **config},
    }


def _router(device_id: str, name: str, x: int, y: int, **config: Any) -> dict[str, Any]:
    return {
        "id": device_id,
        "kind": "router",
        "name": name,
        "position": {"x": x, "y": y},
        "config": {"hostname": name, **config},
    }


def _link(
    link_id: str,
    a_device: str,
    a_interface: str,
    b_device: str,
    b_interface: str,
    cable: str = "straight_through",
) -> dict[str, Any]:
    return {
        "id": link_id,
        "source": {"deviceId": a_device, "interface": a_interface},
        "target": {"deviceId": b_device, "interface": b_interface},
        "cable": cable,
    }


def _document(devices: list[dict[str, Any]], links: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "devices": devices,
        "links": links,
        "groups": [],
        "viewport": {"x": 0, "y": 0, "zoom": 1},
    }


# --------------------------------------------------------------------------- #
# 1. Guided — a flat LAN
# --------------------------------------------------------------------------- #
FIRST_LAN: dict[str, Any] = {
    "slug": "your-first-lan",
    "title": "Build your first LAN",
    "description": (
        "Two PCs and a switch. Give both hosts an address in the same subnet "
        "and prove they can talk to each other."
    ),
    "kind": "guided",
    "scenario_type": "home",
    "difficulty": "beginner",
    "estimated_minutes": 15,
    "passing_score": 80,
    "xp_reward": 40,
    "requirements": [
        "Both PCs are already cabled to the switch.",
        "Use the 192.168.10.0/24 network.",
        "PC1 takes 192.168.10.11 and PC2 takes 192.168.10.12.",
    ],
    "objectives": [
        {
            "id": "address-pc1",
            "title": "Give PC1 the address 192.168.10.11/24",
            "hint": "Double-click PC1, open the Interfaces tab, and fill in Ethernet0.",
            "points": 20,
        },
        {
            "id": "address-pc2",
            "title": "Give PC2 the address 192.168.10.12/24",
            "hint": "Same again on PC2. The mask must match PC1's — 255.255.255.0.",
            "points": 20,
        },
        {
            "id": "reachability",
            "title": "PC1 can ping PC2",
            "hint": (
                "Two hosts on one switch need no gateway at all — only matching "
                "subnets. Check both masks if the ping fails."
            ),
            "points": 30,
        },
    ],
    "initial_topology": _document(
        [
            _pc("pc1", "PC1", 60, 200),
            _switch("sw1", "SW1", 320, 200),
            _pc("pc2", "PC2", 580, 200),
        ],
        [
            _link("l1", "pc1", "Ethernet0", "sw1", "FastEthernet0/1"),
            _link("l2", "sw1", "FastEthernet0/2", "pc2", "Ethernet0"),
        ],
    ),
    "grading_rules": [
        {
            "id": "pc1-address",
            "type": "interface_address",
            "objectiveId": "address-pc1",
            "device": "PC1",
            "interface": "Ethernet0",
            "address": "192.168.10.11",
            "mask": "255.255.255.0",
            "points": 20,
        },
        {
            "id": "pc2-address",
            "type": "interface_address",
            "objectiveId": "address-pc2",
            "device": "PC2",
            "interface": "Ethernet0",
            "address": "192.168.10.12",
            "mask": "255.255.255.0",
            "points": 20,
        },
        {
            "id": "pc1-pings-pc2",
            "type": "ping",
            "objectiveId": "reachability",
            "source": "PC1",
            "destination": "192.168.10.12",
            "points": 30,
        },
    ],
    "fault_injections": [],
}


# --------------------------------------------------------------------------- #
# 2. Challenge — routing between two subnets
# --------------------------------------------------------------------------- #
TWO_SUBNETS: dict[str, Any] = {
    "slug": "route-between-two-subnets",
    "title": "Route between two subnets",
    "description": (
        "A router joins two LANs. Configure both of its interfaces and point "
        "each host at the right gateway."
    ),
    "kind": "challenge",
    "scenario_type": "small_office",
    "difficulty": "intermediate",
    "estimated_minutes": 25,
    "passing_score": 80,
    "xp_reward": 60,
    "requirements": [
        "Left LAN: 192.168.1.0/24, gateway 192.168.1.1.",
        "Right LAN: 10.0.0.0/24, gateway 10.0.0.1.",
        "PC1 is 192.168.1.10 and SRV1 is 10.0.0.10 — both are already set.",
        "Router interfaces start administratively down, as real ones do.",
    ],
    "objectives": [
        {
            "id": "router-left",
            "title": "Configure and enable R1 Gi0/0 as 192.168.1.1/24",
            "hint": "A router interface needs 'no shutdown' before it carries traffic.",
            "points": 20,
        },
        {
            "id": "router-right",
            "title": "Configure and enable R1 Gi0/1 as 10.0.0.1/24",
            "hint": "Same interface, other side. Do not forget 'no shutdown' here either.",
            "points": 20,
        },
        {
            "id": "gateways",
            "title": "Point PC1 and SRV1 at their gateways",
            "hint": (
                "A host sends anything outside its own subnet to its default "
                "gateway. PC1's gateway is the router leg on PC1's own network."
            ),
            "points": 20,
        },
        {
            "id": "end-to-end",
            "title": "PC1 can ping SRV1 across the router",
            "hint": (
                "Both directions have to work. If the request arrives but nothing "
                "comes back, check the gateway on the far side."
            ),
            "points": 30,
        },
    ],
    "initial_topology": _document(
        [
            _pc("pc1", "PC1", 40, 200, ip="192.168.1.10"),
            _switch("sw1", "SW1", 240, 200),
            _router("r1", "R1", 440, 200),
            _switch("sw2", "SW2", 640, 200),
            _server("srv1", "SRV1", 840, 200, ip="10.0.0.10"),
        ],
        [
            _link("l1", "pc1", "Ethernet0", "sw1", "FastEthernet0/1"),
            _link("l2", "sw1", "GigabitEthernet0/1", "r1", "GigabitEthernet0/0"),
            _link("l3", "r1", "GigabitEthernet0/1", "sw2", "GigabitEthernet0/1"),
            _link("l4", "sw2", "FastEthernet0/1", "srv1", "Ethernet0"),
        ],
    ),
    "grading_rules": [
        {
            "id": "r1-gi00",
            "type": "interface_address",
            "objectiveId": "router-left",
            "device": "R1",
            "interface": "GigabitEthernet0/0",
            "address": "192.168.1.1",
            "mask": "255.255.255.0",
            "enabled": True,
            "points": 20,
        },
        {
            "id": "r1-gi01",
            "type": "interface_address",
            "objectiveId": "router-right",
            "device": "R1",
            "interface": "GigabitEthernet0/1",
            "address": "10.0.0.1",
            "mask": "255.255.255.0",
            "enabled": True,
            "points": 20,
        },
        {
            "id": "pc1-gateway",
            "type": "gateway",
            "objectiveId": "gateways",
            "device": "PC1",
            "gateway": "192.168.1.1",
            "points": 10,
        },
        {
            "id": "srv1-gateway",
            "type": "gateway",
            "objectiveId": "gateways",
            "device": "SRV1",
            "gateway": "10.0.0.1",
            "points": 10,
        },
        {
            "id": "pc1-pings-srv1",
            "type": "ping",
            "objectiveId": "end-to-end",
            "source": "PC1",
            "destination": "10.0.0.10",
            "points": 30,
        },
    ],
    "fault_injections": [],
}


# --------------------------------------------------------------------------- #
# 3. Troubleshooting — a working network, broken
# --------------------------------------------------------------------------- #
BROKEN_OFFICE: dict[str, Any] = {
    "slug": "the-office-cannot-reach-the-server",
    "title": "The office cannot reach the server",
    "description": (
        "This network worked yesterday. Nobody in the office can reach the file "
        "server this morning. Find what changed and put it right."
    ),
    "kind": "troubleshooting",
    "scenario_type": "small_office",
    "difficulty": "intermediate",
    "estimated_minutes": 30,
    "passing_score": 100,
    "xp_reward": 80,
    "requirements": [
        "PC1 must be able to ping the file server on 10.0.0.10.",
        "Do not redesign the network — the addressing plan is correct as documented.",
        "Documented plan: office LAN 192.168.1.0/24 (gateway .1), "
        "server LAN 10.0.0.0/24 (gateway .1).",
    ],
    "objectives": [
        {
            "id": "restore-service",
            "title": "PC1 can reach the file server again",
            "hint": (
                "Run a ping in the Simulate panel and read the trace — it names "
                "the device and interface where the packet stops. There is more "
                "than one fault."
            ),
            "points": 60,
        },
        {
            "id": "plan-intact",
            "title": "The documented addressing plan is intact",
            "hint": (
                "Compare each interface against the plan in the requirements. "
                "An address that does not match its subnet is a fault, not a "
                "design choice."
            ),
            "points": 40,
        },
    ],
    "initial_topology": _document(
        [
            _pc("pc1", "PC1", 40, 200, ip="192.168.1.10", gateway="192.168.1.1"),
            _switch("sw1", "SW1", 240, 200),
            _router(
                "r1",
                "R1",
                440,
                200,
                interfaces={
                    "GigabitEthernet0/0": {
                        "ipAddress": "192.168.1.1",
                        "subnetMask": "255.255.255.0",
                        "enabled": True,
                    },
                    "GigabitEthernet0/1": {
                        "ipAddress": "10.0.0.1",
                        "subnetMask": "255.255.255.0",
                        "enabled": True,
                    },
                },
            ),
            _switch("sw2", "SW2", 640, 200),
            _server("srv1", "SRV1", 840, 200, ip="10.0.0.10", gateway="10.0.0.1"),
        ],
        [
            _link("l1", "pc1", "Ethernet0", "sw1", "FastEthernet0/1"),
            _link("l2", "sw1", "GigabitEthernet0/1", "r1", "GigabitEthernet0/0"),
            _link("l3", "r1", "GigabitEthernet0/1", "sw2", "GigabitEthernet0/1"),
            _link("l4", "sw2", "FastEthernet0/1", "srv1", "Ethernet0"),
        ],
    ),
    "grading_rules": [
        {
            "id": "pc1-reaches-server",
            "type": "ping",
            "objectiveId": "restore-service",
            "source": "PC1",
            "destination": "10.0.0.10",
            "points": 60,
        },
        {
            "id": "r1-office-leg",
            "type": "interface_address",
            "objectiveId": "plan-intact",
            "device": "R1",
            "interface": "GigabitEthernet0/0",
            "address": "192.168.1.1",
            "mask": "255.255.255.0",
            "enabled": True,
            "points": 20,
        },
        {
            "id": "pc1-gateway",
            "type": "gateway",
            "objectiveId": "plan-intact",
            "device": "PC1",
            "gateway": "192.168.1.1",
            "points": 20,
        },
    ],
    "fault_injections": [
        {
            "id": "server-leg-shut",
            "type": "shutdown_interface",
            "device": "R1",
            "interface": "GigabitEthernet0/1",
            "explanation": (
                "R1's server-side interface Gi0/1 had been shut down. A shut "
                "interface drops off the routing table entirely, which is why "
                "the trace stopped at R1 rather than at the server."
            ),
        },
        {
            "id": "pc1-bad-gateway",
            "type": "wrong_gateway",
            "device": "PC1",
            "gateway": "192.168.1.254",
            "explanation": (
                "PC1's default gateway had been changed to 192.168.1.254, an "
                "address no device owns — so its ARP for the gateway timed out "
                "before any packet could leave the LAN."
            ),
        },
    ],
}


# --------------------------------------------------------------------------- #
# 4. Design — VLAN segmentation
# --------------------------------------------------------------------------- #
VLAN_SEGMENTATION: dict[str, Any] = {
    "slug": "separate-guests-from-staff",
    "title": "Separate guests from staff",
    "description": (
        "One switch, two groups of users. Put staff and guests in separate "
        "VLANs so guest traffic cannot reach the staff network."
    ),
    "kind": "design",
    "scenario_type": "school",
    "difficulty": "advanced",
    "estimated_minutes": 35,
    "passing_score": 80,
    "xp_reward": 90,
    "requirements": [
        "STAFF1 and STAFF2 belong in VLAN 10; GUEST1 belongs in VLAN 20.",
        "Every host is already addressed in 192.168.5.0/24.",
        "Staff must still be able to reach each other.",
        "Guests must not be able to reach staff at all.",
    ],
    "objectives": [
        {
            "id": "staff-vlan",
            "title": "Put both staff ports in VLAN 10",
            "hint": (
                "On the switch, set each port to access mode and give it VLAN 10. "
                "A trunk port would carry both VLANs and defeat the exercise."
            ),
            "points": 30,
        },
        {
            "id": "guest-vlan",
            "title": "Put the guest port in VLAN 20",
            "hint": "Same idea, VLAN 20. A different VLAN is a different broadcast domain.",
            "points": 20,
        },
        {
            "id": "staff-together",
            "title": "STAFF1 can still reach STAFF2",
            "hint": "Same VLAN and same subnet means they talk directly, with no router.",
            "points": 25,
        },
        {
            "id": "guest-isolated",
            "title": "GUEST1 cannot reach STAFF1",
            "hint": (
                "This one passes when the ping *fails*. If it still works, the "
                "two ports are in the same VLAN."
            ),
            "points": 25,
        },
    ],
    "initial_topology": _document(
        [
            _pc("staff1", "STAFF1", 60, 100, ip="192.168.5.11"),
            _pc("staff2", "STAFF2", 60, 260, ip="192.168.5.12"),
            _pc("guest1", "GUEST1", 60, 420, ip="192.168.5.21"),
            _switch("sw1", "SW1", 400, 260),
        ],
        [
            _link("l1", "staff1", "Ethernet0", "sw1", "FastEthernet0/1"),
            _link("l2", "staff2", "Ethernet0", "sw1", "FastEthernet0/2"),
            _link("l3", "guest1", "Ethernet0", "sw1", "FastEthernet0/3"),
        ],
    ),
    "grading_rules": [
        {
            "id": "staff1-vlan",
            "type": "vlan",
            "objectiveId": "staff-vlan",
            "device": "SW1",
            "interface": "FastEthernet0/1",
            "vlan": 10,
            "points": 15,
        },
        {
            "id": "staff2-vlan",
            "type": "vlan",
            "objectiveId": "staff-vlan",
            "device": "SW1",
            "interface": "FastEthernet0/2",
            "vlan": 10,
            "points": 15,
        },
        {
            "id": "guest1-vlan",
            "type": "vlan",
            "objectiveId": "guest-vlan",
            "device": "SW1",
            "interface": "FastEthernet0/3",
            "vlan": 20,
            "points": 20,
        },
        {
            "id": "staff-reach",
            "type": "ping",
            "objectiveId": "staff-together",
            "source": "STAFF1",
            "destination": "192.168.5.12",
            "points": 25,
        },
        {
            "id": "guest-isolated",
            "type": "no_ping",
            "objectiveId": "guest-isolated",
            "source": "GUEST1",
            "destination": "192.168.5.11",
            "message": "Guest traffic still reaches the staff network.",
            "points": 25,
        },
    ],
    "fault_injections": [],
}


LABS: list[dict[str, Any]] = [
    FIRST_LAN,
    TWO_SUBNETS,
    BROKEN_OFFICE,
    VLAN_SEGMENTATION,
]
