"""Fault injection for troubleshooting labs.

A troubleshooting lab is authored as a **working** network plus a list of things
to break. That is the right way round: an author can verify the topology passes
its own grading rules before breaking it, and the same faults can be reused
across labs.

The faults are applied **server-side, once, when the attempt starts**, and the
fault list is never included in any learner-facing payload. This mirrors how
quiz answer keys are withheld — a lab whose faults are in the JSON the browser
already downloaded is not a troubleshooting exercise, it is a reading exercise.

Each fault mutates the document the way a real mistake would: a shut interface
is `enabled: false` in the interface config, not a special "faulted" flag. The
learner fixes it with `no shutdown` like anything else, and nothing downstream —
the CLI, the config forms, the simulator — needs to know a fault engine exists.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.models.enums import CableKind
from app.schemas.lab import (
    DisableLinkFault,
    RemoveStaticRouteFault,
    ShutdownInterfaceFault,
    WrongAddressFault,
    WrongCableFault,
    WrongGatewayFault,
    WrongVlanFault,
)
from app.schemas.topology import TopologyDevice, TopologyDocument, TopologyLink

logger = get_logger(__name__)


def _find_device(document: TopologyDocument, reference: str) -> TopologyDevice | None:
    """Resolve a device by name (case-insensitive) or id, as rules do."""
    wanted = reference.strip().lower()
    for device in document.devices:
        if device.name.strip().lower() == wanted:
            return device
    return next((device for device in document.devices if device.id == reference), None)


def _find_link(document: TopologyDocument, source: str, destination: str) -> TopologyLink | None:
    a = _find_device(document, source)
    b = _find_device(document, destination)
    if a is None or b is None:
        return None
    ends = {a.id, b.id}
    return next(
        (link for link in document.links if {link.source.device_id, link.target.device_id} == ends),
        None,
    )


def _interface_config(device: TopologyDevice, name: str) -> dict[str, Any]:
    """Get (creating if needed) the config block for one interface."""
    interfaces = device.config.setdefault("interfaces", {})
    if not isinstance(interfaces, dict):  # pragma: no cover - malformed authoring
        interfaces = {}
        device.config["interfaces"] = interfaces
    entry = interfaces.setdefault(name, {})
    if not isinstance(entry, dict):  # pragma: no cover - malformed authoring
        entry = {}
        interfaces[name] = entry
    return entry


def apply_faults(document: TopologyDocument, faults: list[Any]) -> TopologyDocument:
    """Return a copy of `document` with every fault applied.

    Faults that cannot be applied — a device that has since been renamed, a link
    that no longer exists — are logged and skipped rather than raised. A lab
    with one stale fault should still be usable; refusing to start it would be
    the worse failure.
    """
    broken = document.model_copy(deep=True)

    for fault in faults:
        applied = _apply_one(broken, fault)
        if not applied:
            logger.warning(
                "Skipped a fault that no longer matches the topology",
                extra={"fault_id": getattr(fault, "id", "?"), "fault_type": type(fault).__name__},
            )

    return broken


def _apply_one(document: TopologyDocument, fault: Any) -> bool:
    match fault:
        case ShutdownInterfaceFault():
            device = _find_device(document, fault.device)
            if device is None:
                return False
            _interface_config(device, fault.interface)["enabled"] = False
            return True

        case WrongAddressFault():
            device = _find_device(document, fault.device)
            if device is None:
                return False
            entry = _interface_config(device, fault.interface)
            if fault.address is not None:
                entry["ipAddress"] = fault.address
            if fault.mask is not None:
                entry["subnetMask"] = fault.mask
            return True

        case WrongGatewayFault():
            device = _find_device(document, fault.device)
            if device is None:
                return False
            device.config["defaultGateway"] = fault.gateway
            return True

        case WrongVlanFault():
            device = _find_device(document, fault.device)
            if device is None:
                return False
            entry = _interface_config(device, fault.interface)
            entry["switchportMode"] = "access"
            entry["accessVlan"] = fault.vlan
            return True

        case RemoveStaticRouteFault():
            device = _find_device(document, fault.device)
            if device is None:
                return False
            routes = device.config.get("staticRoutes")
            if not isinstance(routes, list) or not routes:
                return False
            if fault.network is None:
                device.config["staticRoutes"] = []
                return True
            remaining = [
                route
                for route in routes
                if not (isinstance(route, dict) and route.get("network") == fault.network)
            ]
            device.config["staticRoutes"] = remaining
            return len(remaining) != len(routes)

        case DisableLinkFault():
            link = _find_link(document, fault.source, fault.destination)
            if link is None:
                return False
            link.enabled = False
            return True

        case WrongCableFault():
            link = _find_link(document, fault.source, fault.destination)
            if link is None:
                return False
            try:
                link.cable = CableKind(fault.cable)
            except ValueError:
                return False
            return True

    return False  # pragma: no cover - the union makes this unreachable
