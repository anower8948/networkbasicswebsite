"""Packet simulation endpoints.

Stateless like the rest of the simulator: the client posts the topology it is
editing and gets back a trace. Nothing is persisted, so a learner can experiment
freely without their scratch work becoming a saved topology.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import Field

from app.api.deps import CurrentUser, DbSession
from app.core.exceptions import NotFoundError, ValidationError
from app.schemas.common import APIModel, ErrorResponse
from app.schemas.topology import TopologyDocument
from app.services.simulation import Network, Simulator
from app.services.simulation.trace import SimulationResult

router = APIRouter(prefix="/simulation", tags=["Simulation"])

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}

Protocol = Literal["ping", "traceroute", "arp", "dhcp", "dns", "tcp", "udp"]


class SimulationRequest(APIModel):
    document: TopologyDocument
    source_device_id: str
    protocol: Protocol = "ping"
    # An IP address or a device name. Unused by DHCP, which broadcasts.
    destination: str = Field(default="", max_length=253)
    port: int = Field(default=80, ge=1, le=65535)
    count: int = Field(default=4, ge=1, le=10)


@router.post(
    "/run",
    response_model=SimulationResult,
    responses=_ERRORS,
    summary="Simulate a protocol exchange and return the full trace",
)
async def run_simulation(
    payload: SimulationRequest,
    session: DbSession,
    user: CurrentUser,
) -> SimulationResult:
    """Run one exchange and return every decision made along the way.

    The trace is the product: a learner runs this to find out *why* something
    failed, so each step records what a device decided and on what grounds.
    """
    if not any(device.id == payload.source_device_id for device in payload.document.devices):
        raise NotFoundError("That device is not in this topology.")

    if payload.protocol != "dhcp" and not payload.destination.strip():
        raise ValidationError("A destination is required for this protocol.")

    network = Network(payload.document)
    simulator = Simulator(network)
    destination = payload.destination.strip()

    match payload.protocol:
        case "ping":
            return simulator.ping(payload.source_device_id, destination, payload.count)
        case "traceroute":
            return simulator.traceroute(payload.source_device_id, destination)
        case "arp":
            return simulator.arp(payload.source_device_id, destination)
        case "dhcp":
            return simulator.dhcp(payload.source_device_id)
        case "dns":
            return simulator.dns(payload.source_device_id, destination)
        case "tcp":
            return simulator.tcp(payload.source_device_id, destination, payload.port)
        case "udp":
            return simulator.udp(payload.source_device_id, destination, payload.port)
