"""Tests for the device configuration and CLI endpoints."""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient

CONFIG = "/api/v1/devices/config"
CLI = "/api/v1/devices/cli"
VIEWS = "/api/v1/devices/views"


def document() -> dict[str, Any]:
    """A router and a switch, cabled together."""
    return {
        "devices": [
            {"id": "r1", "kind": "router", "name": "R1", "position": {"x": 0, "y": 0}},
            {"id": "sw1", "kind": "switch", "name": "SW1", "position": {"x": 240, "y": 0}},
            {"id": "pc1", "kind": "pc", "name": "PC1", "position": {"x": 480, "y": 0}},
        ],
        "links": [
            {
                "id": "l1",
                "source": {"deviceId": "r1", "interface": "GigabitEthernet0/0"},
                "target": {"deviceId": "sw1", "interface": "GigabitEthernet0/1"},
                "cable": "straight_through",
            }
        ],
        "groups": [],
        "viewport": {"x": 0, "y": 0, "zoom": 1},
    }


def blank_session() -> dict[str, Any]:
    return {"mode": "user_exec", "hostname": "Router"}


class TestConfigEndpoint:
    async def test_validates_and_renders_running_config(self, authed_client: AsyncClient) -> None:
        response = await authed_client.post(
            CONFIG,
            json={
                "document": document(),
                "deviceId": "r1",
                "config": {
                    "hostname": "R1",
                    "interfaces": {
                        "GigabitEthernet0/0": {
                            "ipAddress": "192.168.1.1",
                            "subnetMask": "255.255.255.0",
                            "enabled": True,
                        }
                    },
                },
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert "hostname R1" in body["runningConfig"]
        assert "ip address 192.168.1.1 255.255.255.0" in body["runningConfig"]

    async def test_rejects_an_invalid_address(self, authed_client: AsyncClient) -> None:
        response = await authed_client.post(
            CONFIG,
            json={
                "document": document(),
                "deviceId": "r1",
                "config": {"interfaces": {"GigabitEthernet0/0": {"ipAddress": "300.1.1.1"}}},
            },
        )
        assert response.status_code == 422

    async def test_warns_about_an_unreachable_gateway(self, authed_client: AsyncClient) -> None:
        """The classic beginner error: a gateway on no connected network."""
        response = await authed_client.post(
            CONFIG,
            json={
                "document": document(),
                "deviceId": "r1",
                "config": {
                    "defaultGateway": "10.9.9.1",
                    "interfaces": {
                        "GigabitEthernet0/0": {
                            "ipAddress": "192.168.1.1",
                            "subnetMask": "255.255.255.0",
                            "enabled": True,
                        }
                    },
                },
            },
        )

        warnings = response.json()["warnings"]
        assert any("not in any network" in warning for warning in warnings)

    async def test_warns_when_a_configured_interface_is_shut_down(
        self, authed_client: AsyncClient
    ) -> None:
        response = await authed_client.post(
            CONFIG,
            json={
                "document": document(),
                "deviceId": "r1",
                "config": {
                    "interfaces": {
                        "GigabitEthernet0/0": {
                            "ipAddress": "192.168.1.1",
                            "subnetMask": "255.255.255.0",
                            "enabled": False,
                        }
                    }
                },
            },
        )

        warnings = response.json()["warnings"]
        assert any("no shutdown" in warning for warning in warnings)

    async def test_warns_about_a_cabled_but_unaddressed_interface(
        self, authed_client: AsyncClient
    ) -> None:
        response = await authed_client.post(
            CONFIG,
            json={"document": document(), "deviceId": "r1", "config": {}},
        )

        warnings = response.json()["warnings"]
        assert any("cabled but has no IP address" in warning for warning in warnings)

    async def test_warns_about_two_interfaces_in_one_subnet(
        self, authed_client: AsyncClient
    ) -> None:
        response = await authed_client.post(
            CONFIG,
            json={
                "document": document(),
                "deviceId": "r1",
                "config": {
                    "interfaces": {
                        "GigabitEthernet0/0": {
                            "ipAddress": "192.168.1.1",
                            "subnetMask": "255.255.255.0",
                            "enabled": True,
                        },
                        "GigabitEthernet0/1": {
                            "ipAddress": "192.168.1.2",
                            "subnetMask": "255.255.255.0",
                            "enabled": True,
                        },
                    }
                },
            },
        )

        warnings = response.json()["warnings"]
        assert any("its own subnet" in warning for warning in warnings)

    async def test_unknown_device_is_404(self, authed_client: AsyncClient) -> None:
        response = await authed_client.post(
            CONFIG, json={"document": document(), "deviceId": "ghost", "config": {}}
        )
        assert response.status_code == 404

    async def test_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.post(
            CONFIG, json={"document": document(), "deviceId": "r1", "config": {}}
        )
        assert response.status_code == 401


class TestCliEndpoint:
    async def test_executes_a_command_and_returns_the_prompt(
        self, authed_client: AsyncClient
    ) -> None:
        response = await authed_client.post(
            CLI,
            json={
                "document": document(),
                "deviceId": "r1",
                "command": "enable",
                "session": blank_session(),
                "config": {},
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["session"]["mode"] == "priv_exec"
        assert body["prompt"].endswith("#")

    async def test_a_configuration_command_updates_the_config(
        self, authed_client: AsyncClient
    ) -> None:
        session = blank_session()
        config: dict[str, Any] = {}

        for command in [
            "enable",
            "configure terminal",
            "interface GigabitEthernet0/0",
            "ip address 192.168.1.1 255.255.255.0",
            "no shutdown",
        ]:
            response = await authed_client.post(
                CLI,
                json={
                    "document": document(),
                    "deviceId": "r1",
                    "command": command,
                    "session": session,
                    "config": config,
                },
            )
            assert response.status_code == 200
            body = response.json()
            session, config = body["session"], body["config"]

        interface = config["interfaces"]["GigabitEthernet0/0"]
        assert interface["ipAddress"] == "192.168.1.1"
        assert interface["enabled"] is True

    async def test_reports_whether_the_config_changed(self, authed_client: AsyncClient) -> None:
        """The editor uses this to mark the topology dirty."""
        response = await authed_client.post(
            CLI,
            json={
                "document": document(),
                "deviceId": "r1",
                "command": "enable",
                "session": blank_session(),
                "config": {},
            },
        )
        assert response.json()["changed"] is False

        response = await authed_client.post(
            CLI,
            json={
                "document": document(),
                "deviceId": "r1",
                "command": "hostname R1",
                "session": {"mode": "global_config", "hostname": "Router"},
                "config": {},
            },
        )
        assert response.json()["changed"] is True

    async def test_a_device_without_a_cli_is_rejected(self, authed_client: AsyncClient) -> None:
        response = await authed_client.post(
            CLI,
            json={
                "document": document(),
                "deviceId": "pc1",
                "command": "enable",
                "session": blank_session(),
                "config": {},
            },
        )

        assert response.status_code == 422
        assert "command-line" in response.json()["error"]["message"]

    async def test_prompt_follows_a_hostname_set_through_the_form(
        self, authed_client: AsyncClient
    ) -> None:
        """A hostname set in the form must show in the terminal prompt."""
        response = await authed_client.post(
            CLI,
            json={
                "document": document(),
                "deviceId": "r1",
                "command": "enable",
                "session": blank_session(),
                "config": {"hostname": "CoreRouter"},
            },
        )

        assert response.json()["prompt"] == "CoreRouter#"


class TestViewsEndpoint:
    async def test_returns_all_three_show_outputs(self, authed_client: AsyncClient) -> None:
        response = await authed_client.post(
            VIEWS,
            json={
                "document": document(),
                "deviceId": "r1",
                "config": {
                    "interfaces": {
                        "GigabitEthernet0/0": {
                            "ipAddress": "10.0.0.1",
                            "subnetMask": "255.255.255.0",
                            "enabled": True,
                        }
                    }
                },
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert "interface GigabitEthernet0/0" in body["runningConfig"]
        assert "10.0.0.1" in body["interfaceBrief"]
        assert "directly connected" in body["ipRoute"]
