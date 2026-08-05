"""The topology document.

Part 1 chose to store a saved network as one JSON document rather than
normalised tables, on the grounds that the editor always reads and writes a
whole topology and the shape would change quickly through Parts 4–7. This is
the schema that makes that choice safe: the document is fully validated on the
way in, so "schemaless storage" never means unvalidated input.

Validation is **structural**, not merely per-field:

* every link endpoint must name a device that exists
* every interface must exist on that device's kind
* an interface can carry at most one link — you cannot plug two cables into
  one port
* device and link ids must be unique
* a link cannot join a device to itself on the same interface

Configuration of those interfaces (addresses, VLANs, routing) is Part 5 and
lives in `TopologyDevice.config`, which is deliberately untyped here.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import CableKind, DeviceKind
from app.schemas.common import APIModel
from app.services.device_catalog import cable_warning, spec_for

# Bumped when the document format changes incompatibly. Mirrors
# `app.models.lab.TOPOLOGY_SCHEMA_VERSION`.
TOPOLOGY_SCHEMA_VERSION = 1

MAX_DEVICES = 200
MAX_LINKS = 400


class DocumentModel(BaseModel):
    """Documents round-trip verbatim, so unknown keys are rejected rather than
    silently dropped on the next save."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Position(DocumentModel):
    x: float = Field(ge=-100_000, le=100_000)
    y: float = Field(ge=-100_000, le=100_000)


class TopologyDevice(DocumentModel):
    id: str = Field(min_length=1, max_length=64)
    kind: DeviceKind
    name: str = Field(min_length=1, max_length=64)
    position: Position
    # Free-text note shown under the device on the canvas.
    label: str | None = Field(default=None, max_length=120)
    group_id: str | None = Field(default=None, max_length=64, alias="groupId")
    # Per-interface and device configuration. Typed in Part 5; kept opaque here
    # so the editor can round-trip it without this schema needing to know the
    # shape of an ACL.
    config: dict[str, Any] = Field(default_factory=dict)

    def interface_names(self) -> set[str]:
        return {str(entry["name"]) for entry in spec_for(self.kind).interfaces()}


class LinkEndpoint(DocumentModel):
    device_id: str = Field(min_length=1, max_length=64, alias="deviceId")
    interface: str = Field(min_length=1, max_length=64)


class TopologyLink(DocumentModel):
    id: str = Field(min_length=1, max_length=64)
    source: LinkEndpoint
    target: LinkEndpoint
    cable: CableKind = CableKind.STRAIGHT_THROUGH
    # Set false to model an unplugged or failed cable. Part 8's troubleshooting
    # mode flips this to inject a fault.
    enabled: bool = True
    label: str | None = Field(default=None, max_length=120)


class TopologyGroup(DocumentModel):
    """A labelled boundary drawn behind devices — a building, floor or VLAN."""

    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=80)
    position: Position
    width: float = Field(default=360, ge=80, le=8000)
    height: float = Field(default=240, ge=80, le=8000)
    color: str | None = Field(default=None, max_length=40)


class Viewport(DocumentModel):
    x: float = 0
    y: float = 0
    zoom: float = Field(default=1, ge=0.1, le=4)


class LinkIssue(APIModel):
    """A non-fatal problem with a link, surfaced to the learner as a warning."""

    link_id: str
    message: str


class TopologyDocument(DocumentModel):
    """A complete saved network."""

    schema_version: int = Field(default=TOPOLOGY_SCHEMA_VERSION, alias="schemaVersion")
    devices: list[TopologyDevice] = Field(default_factory=list, max_length=MAX_DEVICES)
    links: list[TopologyLink] = Field(default_factory=list, max_length=MAX_LINKS)
    groups: list[TopologyGroup] = Field(default_factory=list, max_length=50)
    viewport: Viewport = Field(default_factory=Viewport)

    @model_validator(mode="after")
    def _validate_structure(self) -> TopologyDocument:
        devices_by_id: dict[str, TopologyDevice] = {}
        for device in self.devices:
            if device.id in devices_by_id:
                raise ValueError(f"Duplicate device id: {device.id}")
            devices_by_id[device.id] = device

        group_ids = {group.id for group in self.groups}
        if len(group_ids) != len(self.groups):
            raise ValueError("Duplicate group id")

        for device in self.devices:
            if device.group_id is not None and device.group_id not in group_ids:
                raise ValueError(f"Device {device.name} references unknown group {device.group_id}")

        seen_links: set[str] = set()
        # An interface takes one cable. Tracking occupancy here is what stops a
        # topology that looks fine on screen from being physically impossible.
        occupied: dict[tuple[str, str], str] = {}

        for link in self.links:
            if link.id in seen_links:
                raise ValueError(f"Duplicate link id: {link.id}")
            seen_links.add(link.id)

            for side, endpoint in (("source", link.source), ("target", link.target)):
                # Named distinctly from the `device` loop above, which binds a
                # non-optional TopologyDevice.
                endpoint_device = devices_by_id.get(endpoint.device_id)
                if endpoint_device is None:
                    raise ValueError(
                        f"Link {link.id} {side} references unknown device {endpoint.device_id}"
                    )
                if endpoint.interface not in endpoint_device.interface_names():
                    raise ValueError(
                        f"Link {link.id} {side}: {endpoint_device.name} has no interface "
                        f"{endpoint.interface}"
                    )

                slot = (endpoint.device_id, endpoint.interface)
                if slot in occupied:
                    raise ValueError(
                        f"{endpoint_device.name} {endpoint.interface} already carries link "
                        f"{occupied[slot]}"
                    )
                occupied[slot] = link.id

            if (
                link.source.device_id == link.target.device_id
                and link.source.interface == link.target.interface
            ):
                raise ValueError(f"Link {link.id} joins an interface to itself")

        return self

    def cable_issues(self) -> list[LinkIssue]:
        """Miscabled links, as advisory warnings.

        Not raised during validation: a learner is allowed to save a topology
        with the wrong cable and discover the consequence. Part 7 will refuse to
        forward traffic across one.
        """
        devices_by_id = {device.id: device for device in self.devices}
        issues: list[LinkIssue] = []

        for link in self.links:
            source = devices_by_id.get(link.source.device_id)
            target = devices_by_id.get(link.target.device_id)
            if source is None or target is None:
                continue

            message = cable_warning(
                source.kind,
                link.source.interface,
                target.kind,
                link.target.interface,
                link.cable,
            )
            if message is not None:
                issues.append(LinkIssue(link_id=link.id, message=message))

        return issues


# --------------------------------------------------------------------------- #
# API models
# --------------------------------------------------------------------------- #
class TopologySummary(APIModel):
    """Card-sized projection for the topology list — excludes the document."""

    id: uuid.UUID
    name: str
    description: str | None
    device_count: int
    schema_version: int
    is_template: bool
    is_public: bool
    thumbnail_url: str | None
    created_at: Any
    updated_at: Any


class TopologyRead(TopologySummary):
    document: TopologyDocument
    # Advisory cabling problems, recomputed on every read.
    issues: list[LinkIssue] = []


class TopologyCreate(APIModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    document: TopologyDocument = Field(default_factory=TopologyDocument)


class TopologyUpdate(APIModel):
    """Partial update. Omitted fields are left untouched."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    document: TopologyDocument | None = None


class TopologyImport(APIModel):
    """An exported file being brought back in."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    document: TopologyDocument


class LinkSuggestion(APIModel):
    """What the editor should use when two devices are joined."""

    source_interface: str
    target_interface: str
    cable: CableKind
    warning: str | None = None
