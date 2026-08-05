"""Device configuration and CLI endpoints.

Both operate on a device **inside a topology document**, and both are stateless:
the client posts the document it is editing and receives the updated one back.
That keeps the editor's unsaved-changes model intact — configuring a device does
not silently persist a topology the learner has not saved.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.core.exceptions import NotFoundError, ValidationError
from app.models.enums import DeviceKind
from app.schemas.common import APIModel, ErrorResponse
from app.schemas.device_config import DeviceConfig, admin_up
from app.schemas.topology import TopologyDocument
from app.services.cli import CliEngine, CliSession
from app.services.device_catalog import spec_for
from app.services.running_config import (
    render_interface_brief,
    render_ip_route,
    render_running_config,
)
from app.services.simulation import Network

router = APIRouter(prefix="/devices", tags=["Devices"])

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}


# --------------------------------------------------------------------------- #
# Payloads
# --------------------------------------------------------------------------- #
class DeviceConfigRequest(APIModel):
    """A device's configuration in the context of its topology."""

    document: TopologyDocument
    device_id: str
    config: DeviceConfig


class DeviceConfigResponse(APIModel):
    device_id: str
    config: DeviceConfig
    running_config: str
    # Non-fatal problems: a gateway outside every connected subnet, an
    # unaddressed but cabled interface, and so on.
    warnings: list[str] = []


class CliRequest(APIModel):
    document: TopologyDocument
    device_id: str
    command: str
    session: CliSession
    config: DeviceConfig


class CliResponse(APIModel):
    """One command's result."""

    output: str
    session: CliSession
    config: DeviceConfig
    # Prompt for the *next* line, so the terminal need not model IOS modes.
    prompt: str
    changed: bool


class DeviceViewResponse(APIModel):
    """Read-only views a configuration window shows alongside the forms."""

    running_config: str
    interface_brief: str
    ip_route: str


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _device_kind(document: TopologyDocument, device_id: str) -> DeviceKind:
    for device in document.devices:
        if device.id == device_id:
            return device.kind
    raise NotFoundError("That device is not in this topology.")


def _config_warnings(document: TopologyDocument, device_id: str, config: DeviceConfig) -> list[str]:
    """Advisory configuration problems.

    Warnings, not errors: a half-finished configuration is a normal state while
    someone is learning, and refusing to save it would be hostile. Part 7 will
    turn these into observable failures when traffic does not flow.
    """
    import ipaddress

    warnings: list[str] = []
    kind = _device_kind(document, device_id)
    spec = spec_for(kind)

    connected = config.configured_networks(kind.value)

    # A gateway nobody can reach is the classic beginner error.
    if config.default_gateway and connected:
        gateway = ipaddress.IPv4Address(config.default_gateway)
        if not any(gateway in network for _, network in connected):
            warnings.append(
                f"The default gateway {config.default_gateway} is not in any "
                "network this device is connected to."
            )

    # Cabled but unaddressed, or addressed but shut down.
    cabled = {
        endpoint.interface
        for link in document.links
        for endpoint in (link.source, link.target)
        if endpoint.device_id == device_id
    }
    for name in cabled:
        interface = config.interfaces.get(name)
        if interface is None or (not interface.ip_address and not interface.dhcp):
            if spec.is_endpoint or kind in (DeviceKind.ROUTER, DeviceKind.FIREWALL):
                warnings.append(f"{name} is cabled but has no IP address.")
        elif not admin_up(interface, kind.value):
            warnings.append(
                f"{name} is configured but administratively down — it needs 'no shutdown'."
            )

    # Two interfaces in the same subnet cannot both forward.
    seen: dict[str, str] = {}
    for name, network in connected:
        key = str(network)
        if key in seen:
            warnings.append(
                f"{name} and {seen[key]} are both in {key}; each interface needs its own subnet."
            )
        seen[key] = name

    return warnings


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@router.post(
    "/config",
    response_model=DeviceConfigResponse,
    responses=_ERRORS,
    summary="Validate a device configuration and render its running config",
)
async def save_config(
    payload: DeviceConfigRequest,
    session: DbSession,
    user: CurrentUser,
) -> DeviceConfigResponse:
    """Validates the configuration and returns it with `show run` output.

    Nothing is persisted here — the caller writes the returned configuration
    back into its topology document and saves that when ready.
    """
    kind = _device_kind(payload.document, payload.device_id)

    return DeviceConfigResponse(
        device_id=payload.device_id,
        config=payload.config,
        running_config=render_running_config(payload.config, kind),
        warnings=_config_warnings(payload.document, payload.device_id, payload.config),
    )


@router.post(
    "/views",
    response_model=DeviceViewResponse,
    responses=_ERRORS,
    summary="Rendered show-command output for a device",
)
async def device_views(
    payload: DeviceConfigRequest,
    session: DbSession,
    user: CurrentUser,
) -> DeviceViewResponse:
    kind = _device_kind(payload.document, payload.device_id)
    return DeviceViewResponse(
        running_config=render_running_config(payload.config, kind),
        interface_brief=render_interface_brief(payload.config, kind),
        ip_route=render_ip_route(payload.config, kind),
    )


@router.post(
    "/cli",
    response_model=CliResponse,
    responses=_ERRORS,
    summary="Execute one Cisco IOS command",
)
async def execute_command(
    payload: CliRequest,
    session: DbSession,
    user: CurrentUser,
) -> CliResponse:
    """Run a command against a device.

    Stateless: the terminal holds the session (mode, selected interface) and
    sends it with every line, so no server-side connection state exists to
    expire or leak.
    """
    kind = _device_kind(payload.document, payload.device_id)
    spec = spec_for(kind)
    if not spec.has_cli:
        raise ValidationError(f"A {spec.label.lower()} has no command-line interface.")

    # Give the engine the topology so `ping` runs the real packet engine
    # rather than reporting that it cannot.
    engine = CliEngine(kind, network=Network(payload.document), device_id=payload.device_id)

    # Keep the prompt in step with a hostname set through the forms.
    incoming = payload.session
    if payload.config.hostname and incoming.hostname != payload.config.hostname:
        incoming = incoming.model_copy(update={"hostname": payload.config.hostname})

    result = engine.execute(payload.command, incoming, payload.config)

    return CliResponse(
        output=result.output,
        session=result.session,
        config=result.config,
        prompt=result.session.prompt(),
        changed=result.changed,
    )
