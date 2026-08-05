"""CLI session state.

The session is **stateless on the server**: the client holds it and sends it
with each command. A terminal is a long conversation, and storing per-connection
state server-side would need sticky sessions, expiry and cleanup for something
that is a handful of fields.

What a session tracks is exactly what IOS tracks: which mode you are in, and
which object you are configuring inside it.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from app.schemas.common import APIModel


class CliMode(StrEnum):
    """IOS configuration modes, in the order you descend through them."""

    USER_EXEC = "user_exec"
    PRIV_EXEC = "priv_exec"
    GLOBAL_CONFIG = "global_config"
    INTERFACE_CONFIG = "interface_config"
    VLAN_CONFIG = "vlan_config"
    ROUTER_CONFIG = "router_config"
    LINE_CONFIG = "line_config"
    DHCP_CONFIG = "dhcp_config"


# Which mode `exit` returns to. `end` always jumps straight to privileged EXEC.
PARENT_MODE: dict[CliMode, CliMode] = {
    CliMode.USER_EXEC: CliMode.USER_EXEC,
    CliMode.PRIV_EXEC: CliMode.USER_EXEC,
    CliMode.GLOBAL_CONFIG: CliMode.PRIV_EXEC,
    CliMode.INTERFACE_CONFIG: CliMode.GLOBAL_CONFIG,
    CliMode.VLAN_CONFIG: CliMode.GLOBAL_CONFIG,
    CliMode.ROUTER_CONFIG: CliMode.GLOBAL_CONFIG,
    CliMode.LINE_CONFIG: CliMode.GLOBAL_CONFIG,
    CliMode.DHCP_CONFIG: CliMode.GLOBAL_CONFIG,
}


class CliSession(APIModel):
    """Where the operator currently is."""

    mode: CliMode = CliMode.USER_EXEC

    # The object being configured in the current mode.
    interface: str | None = None
    vlan_id: int | None = None
    router_protocol: str | None = None
    router_process: int | None = None
    dhcp_pool: str | None = None
    line: str | None = None

    # Mirrors the device hostname so the prompt is right without a config lookup.
    hostname: str = Field(default="Router", max_length=63)

    def prompt(self) -> str:
        """The prompt string IOS would show for this state."""
        suffix = {
            CliMode.USER_EXEC: ">",
            CliMode.PRIV_EXEC: "#",
            CliMode.GLOBAL_CONFIG: "(config)#",
            CliMode.INTERFACE_CONFIG: "(config-if)#",
            CliMode.VLAN_CONFIG: "(config-vlan)#",
            CliMode.ROUTER_CONFIG: "(config-router)#",
            CliMode.LINE_CONFIG: "(config-line)#",
            CliMode.DHCP_CONFIG: "(dhcp-config)#",
        }[self.mode]
        return f"{self.hostname}{suffix}"

    def leave(self) -> CliSession:
        """`exit` — step one mode up, clearing the context it belonged to."""
        parent = PARENT_MODE[self.mode]
        return self.model_copy(
            update={
                "mode": parent,
                "interface": None,
                "vlan_id": None,
                "router_protocol": None,
                "router_process": None,
                "dhcp_pool": None,
                "line": None,
            }
        )

    def to_privileged(self) -> CliSession:
        """`end` or Ctrl-Z — jump straight out of configuration mode."""
        return self.model_copy(
            update={
                "mode": CliMode.PRIV_EXEC,
                "interface": None,
                "vlan_id": None,
                "router_protocol": None,
                "router_process": None,
                "dhcp_pool": None,
                "line": None,
            }
        )

    @property
    def in_config(self) -> bool:
        return self.mode not in (CliMode.USER_EXEC, CliMode.PRIV_EXEC)
