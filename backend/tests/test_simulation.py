"""Tests for the packet simulation engine.

These encode what the simulator must teach: not just that a correct network
works, but that each classic misconfiguration fails with a message naming the
actual cause.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from httpx import AsyncClient

from app.schemas.topology import TopologyDocument
from app.services.simulation import Network, Simulator
from app.services.simulation.trace import EventKind


def routed_topology() -> dict[str, Any]:
    """PC1 — SW1 — R1 — SW2 — PC2, across two subnets."""
    return {
        "devices": [
            {
                "id": "pc1",
                "kind": "pc",
                "name": "PC1",
                "position": {"x": 0, "y": 0},
                "config": {
                    "interfaces": {
                        "Ethernet0": {
                            "ipAddress": "192.168.1.10",
                            "subnetMask": "255.255.255.0",
                            "enabled": True,
                        }
                    },
                    "defaultGateway": "192.168.1.1",
                },
            },
            {
                "id": "sw1",
                "kind": "switch",
                "name": "SW1",
                "position": {"x": 1, "y": 0},
                "config": {},
            },
            {
                "id": "r1",
                "kind": "router",
                "name": "R1",
                "position": {"x": 2, "y": 0},
                "config": {
                    "hostname": "R1",
                    "interfaces": {
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
                },
            },
            {
                "id": "sw2",
                "kind": "switch",
                "name": "SW2",
                "position": {"x": 3, "y": 0},
                "config": {},
            },
            {
                "id": "pc2",
                "kind": "pc",
                "name": "PC2",
                "position": {"x": 4, "y": 0},
                "config": {
                    "interfaces": {
                        "Ethernet0": {
                            "ipAddress": "10.0.0.10",
                            "subnetMask": "255.255.255.0",
                            "enabled": True,
                        }
                    },
                    "defaultGateway": "10.0.0.1",
                },
            },
        ],
        "links": [
            {
                "id": "l1",
                "source": {"deviceId": "pc1", "interface": "Ethernet0"},
                "target": {"deviceId": "sw1", "interface": "FastEthernet0/1"},
                "cable": "straight_through",
            },
            {
                "id": "l2",
                "source": {"deviceId": "sw1", "interface": "GigabitEthernet0/1"},
                "target": {"deviceId": "r1", "interface": "GigabitEthernet0/0"},
                "cable": "straight_through",
            },
            {
                "id": "l3",
                "source": {"deviceId": "r1", "interface": "GigabitEthernet0/1"},
                "target": {"deviceId": "sw2", "interface": "GigabitEthernet0/1"},
                "cable": "straight_through",
            },
            {
                "id": "l4",
                "source": {"deviceId": "sw2", "interface": "FastEthernet0/1"},
                "target": {"deviceId": "pc2", "interface": "Ethernet0"},
                "cable": "straight_through",
            },
        ],
        "groups": [],
        "viewport": {"x": 0, "y": 0, "zoom": 1},
    }


def simulate(mutate: Callable[[dict[str, Any]], None] | None = None) -> Simulator:
    payload = routed_topology()
    if mutate:
        mutate(payload)
    return Simulator(Network(TopologyDocument.model_validate(payload)))


def last_failure(result: Any) -> Any:
    failures = [event for event in result.events if not event.ok]
    assert failures, "expected at least one failing event"
    return failures[-1]


class TestWorkingNetwork:
    def test_ping_across_a_router_succeeds(self) -> None:
        result = simulate().ping("pc1", "10.0.0.10")

        assert result.success
        assert "4/4 received" in result.summary

    def test_the_trace_shows_the_gateway_decision(self) -> None:
        """The concept being taught: same subnet or not."""
        result = simulate().ping("pc1", "10.0.0.10")

        summaries = [event.summary for event in result.events]
        assert any("not local — sending to the gateway" in text for text in summaries)

    def test_arp_happens_on_each_segment(self) -> None:
        result = simulate().ping("pc1", "10.0.0.10")

        requests = [e for e in result.events if e.kind is EventKind.ARP_REQUEST]
        # PC1→gateway, R1→PC2, and the two on the return path.
        assert len(requests) >= 2

    def test_mac_addresses_are_rewritten_but_ip_addresses_are_not(self) -> None:
        """The single most useful thing a packet trace can show."""
        result = simulate().ping("pc1", "10.0.0.10")

        forwards = [e for e in result.events if e.kind is EventKind.FORWARD and e.frame is not None]
        assert len(forwards) >= 2

        first, second = forwards[0], forwards[1]
        assert first.frame.destination_ip == second.frame.destination_ip  # type: ignore[union-attr]
        assert first.frame.destination_mac != second.frame.destination_mac  # type: ignore[union-attr]

    def test_a_local_ping_needs_no_gateway(self) -> None:
        result = simulate().ping("pc1", "192.168.1.1")

        assert result.success
        assert any("local subnet" in event.summary for event in result.events)

    def test_the_reply_path_is_simulated_too(self) -> None:
        """A one-way path is a real failure mode, so the return leg must run."""
        result = simulate().ping("pc1", "10.0.0.10")
        assert any(event.kind is EventKind.REPLY for event in result.events)

    def test_destinations_can_be_named(self) -> None:
        result = simulate().ping("pc1", "PC2")
        assert result.success


class TestFailureDiagnostics:
    """Each classic mistake must fail with a message naming the real cause."""

    def test_a_host_with_no_gateway_says_so(self) -> None:
        def mutate(payload: dict[str, Any]) -> None:
            payload["devices"][0]["config"].pop("defaultGateway")

        result = simulate(mutate).ping("pc1", "10.0.0.10")

        assert not result.success
        assert "no default gateway" in (result.hint or "")

    def test_a_gateway_nobody_answers_for_reports_arp_timeout(self) -> None:
        def mutate(payload: dict[str, Any]) -> None:
            payload["devices"][0]["config"]["defaultGateway"] = "192.168.1.254"

        result = simulate(mutate).ping("pc1", "10.0.0.10")

        assert not result.success
        failure = last_failure(result)
        assert failure.kind is EventKind.TIMEOUT
        assert "192.168.1.254" in (failure.detail or "")

    def test_a_shut_interface_is_named_rather_than_blamed_on_routing(self) -> None:
        """ "Add a route" would be the wrong advice when the route exists."""

        def mutate(payload: dict[str, Any]) -> None:
            payload["devices"][2]["config"]["interfaces"]["GigabitEthernet0/1"]["enabled"] = False

        result = simulate(mutate).ping("pc1", "10.0.0.10")

        assert not result.success
        detail = last_failure(result).detail or ""
        assert "administratively down" in detail
        assert "no shutdown" in detail

    def test_a_miscabled_link_names_the_cable(self) -> None:
        """The Part 4 warning becomes a real failure here."""

        def mutate(payload: dict[str, Any]) -> None:
            payload["links"][1]["cable"] = "crossover"

        result = simulate(mutate).ping("pc1", "10.0.0.10")

        assert not result.success
        detail = last_failure(result).detail or ""
        assert "crossover" in detail
        assert "wrong type" in detail

    def test_a_disabled_link_is_named(self) -> None:
        def mutate(payload: dict[str, Any]) -> None:
            payload["links"][3]["enabled"] = False

        result = simulate(mutate).ping("pc1", "10.0.0.10")

        assert not result.success
        assert "disabled" in (last_failure(result).detail or "")

    def test_an_unknown_destination_is_rejected(self) -> None:
        result = simulate().ping("pc1", "203.0.113.99")

        assert not result.success
        assert "answers to" in (result.failure_reason or "")

    def test_a_one_way_path_reports_the_return_leg(self) -> None:
        """Reaching the destination is not enough — the reply must get back."""

        def mutate(payload: dict[str, Any]) -> None:
            payload["devices"][4]["config"].pop("defaultGateway")

        result = simulate(mutate).ping("pc1", "10.0.0.10")

        assert not result.success
        assert "reply" in result.summary.lower()


class TestVlanSeparation:
    def test_two_vlans_on_one_switch_cannot_reach_each_other(self) -> None:
        """A VLAN is a separate broadcast domain — that is the whole point."""

        def mutate(payload: dict[str, Any]) -> None:
            # Put both hosts on SW1, in different VLANs.
            payload["devices"][4]["config"]["interfaces"]["Ethernet0"] = {
                "ipAddress": "192.168.1.20",
                "subnetMask": "255.255.255.0",
                "enabled": True,
            }
            payload["devices"][1]["config"] = {
                "vlans": [{"id": 10, "name": "Sales"}, {"id": 20, "name": "Accounts"}],
                "interfaces": {
                    "FastEthernet0/1": {"switchportMode": "access", "accessVlan": 10},
                    "FastEthernet0/2": {"switchportMode": "access", "accessVlan": 20},
                },
            }
            payload["links"] = [
                payload["links"][0],
                {
                    "id": "l5",
                    "source": {"deviceId": "sw1", "interface": "FastEthernet0/2"},
                    "target": {"deviceId": "pc2", "interface": "Ethernet0"},
                    "cable": "straight_through",
                },
            ]

        result = simulate(mutate).ping("pc1", "192.168.1.20")

        assert not result.success
        assert "VLAN" in (last_failure(result).detail or "")

    def test_the_same_vlan_does_reach(self) -> None:
        def mutate(payload: dict[str, Any]) -> None:
            payload["devices"][4]["config"]["interfaces"]["Ethernet0"] = {
                "ipAddress": "192.168.1.20",
                "subnetMask": "255.255.255.0",
                "enabled": True,
            }
            payload["devices"][1]["config"] = {
                "vlans": [{"id": 10, "name": "Sales"}],
                "interfaces": {
                    "FastEthernet0/1": {"switchportMode": "access", "accessVlan": 10},
                    "FastEthernet0/2": {"switchportMode": "access", "accessVlan": 10},
                },
            }
            payload["links"] = [
                payload["links"][0],
                {
                    "id": "l5",
                    "source": {"deviceId": "sw1", "interface": "FastEthernet0/2"},
                    "target": {"deviceId": "pc2", "interface": "Ethernet0"},
                    "cable": "straight_through",
                },
            ]

        result = simulate(mutate).ping("pc1", "192.168.1.20")
        assert result.success


class TestProtocols:
    def test_dhcp_completes_the_dora_exchange(self) -> None:
        def mutate(payload: dict[str, Any]) -> None:
            payload["devices"][2]["config"]["dhcpPools"] = [
                {
                    "name": "LAN",
                    "network": "192.168.1.0",
                    "mask": "255.255.255.0",
                    "gateway": "192.168.1.1",
                    "dnsServers": ["8.8.8.8"],
                }
            ]

        result = simulate(mutate).dhcp("pc1")

        assert result.success
        kinds = [event.kind for event in result.events]
        assert kinds == [
            EventKind.DHCP_DISCOVER,
            EventKind.DHCP_OFFER,
            EventKind.DHCP_REQUEST,
            EventKind.DHCP_ACK,
        ]

    def test_dhcp_without_a_pool_mentions_apipa(self) -> None:
        """Explaining the 169.254 address is the lesson when DHCP fails."""
        result = simulate().dhcp("pc1")

        assert not result.success
        assert "169.254" in (result.failure_reason or "")

    def test_dns_resolves_a_device_name(self) -> None:
        def mutate(payload: dict[str, Any]) -> None:
            payload["devices"][0]["config"]["dnsServers"] = ["10.0.0.10"]

        result = simulate(mutate).dns("pc1", "PC2")

        assert result.success
        assert "10.0.0.10" in result.summary

    def test_dns_without_a_resolver_says_so(self) -> None:
        result = simulate().dns("pc1", "PC2")

        assert not result.success
        assert "no DNS server" in (result.failure_reason or "")

    def test_tcp_runs_a_three_way_handshake(self) -> None:
        result = simulate().tcp("pc1", "10.0.0.10", 80)

        assert result.success
        kinds = [event.kind for event in result.events]
        assert EventKind.TCP_SYN in kinds
        assert EventKind.TCP_SYN_ACK in kinds
        assert EventKind.TCP_ACK in kinds

    def test_tcp_closing_is_described_as_four_messages(self) -> None:
        result = simulate().tcp("pc1", "10.0.0.10", 80)

        fin = next(event for event in result.events if event.kind is EventKind.TCP_FIN)
        assert "four" in (fin.detail or "")

    def test_udp_has_no_handshake(self) -> None:
        """The contrast with TCP is the lesson."""
        result = simulate().udp("pc1", "10.0.0.10", 53)

        assert result.success
        kinds = [event.kind for event in result.events]
        assert EventKind.TCP_SYN not in kinds
        assert EventKind.UDP_DATAGRAM in kinds

    def test_udp_loss_is_reported_as_silent(self) -> None:
        def mutate(payload: dict[str, Any]) -> None:
            payload["links"][3]["enabled"] = False

        result = simulate(mutate).udp("pc1", "10.0.0.10", 53)

        assert not result.success
        assert "never told" in (result.hint or "")

    def test_arp_resolves_a_local_address(self) -> None:
        result = simulate().arp("pc1", "192.168.1.1")

        assert result.success
        assert "is at" in result.summary

    def test_traceroute_counts_the_hops(self) -> None:
        result = simulate().traceroute("pc1", "10.0.0.10")

        assert result.success
        assert "hop" in result.summary


class TestAnimationData:
    def test_forwarding_events_carry_a_link_for_the_canvas(self) -> None:
        result = simulate().ping("pc1", "10.0.0.10")

        animated = [event for event in result.events if event.link_id]
        assert animated, "the canvas needs link ids to animate"
        for event in animated:
            assert event.link_id in {"l1", "l2", "l3", "l4"}


class TestSimulationEndpoint:
    async def test_runs_a_ping_and_returns_the_trace(self, authed_client: AsyncClient) -> None:
        response = await authed_client.post(
            "/api/v1/simulation/run",
            json={
                "document": routed_topology(),
                "sourceDeviceId": "pc1",
                "protocol": "ping",
                "destination": "10.0.0.10",
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert len(body["events"]) > 5

    async def test_reports_a_failure_with_a_reason(self, authed_client: AsyncClient) -> None:
        payload = routed_topology()
        payload["devices"][0]["config"].pop("defaultGateway")

        response = await authed_client.post(
            "/api/v1/simulation/run",
            json={
                "document": payload,
                "sourceDeviceId": "pc1",
                "protocol": "ping",
                "destination": "10.0.0.10",
            },
        )

        body = response.json()
        assert body["success"] is False
        assert body["failureReason"]
        assert body["hint"]

    async def test_unknown_source_device_is_404(self, authed_client: AsyncClient) -> None:
        response = await authed_client.post(
            "/api/v1/simulation/run",
            json={
                "document": routed_topology(),
                "sourceDeviceId": "ghost",
                "protocol": "ping",
                "destination": "10.0.0.10",
            },
        )
        assert response.status_code == 404

    async def test_a_missing_destination_is_rejected(self, authed_client: AsyncClient) -> None:
        response = await authed_client.post(
            "/api/v1/simulation/run",
            json={
                "document": routed_topology(),
                "sourceDeviceId": "pc1",
                "protocol": "ping",
                "destination": "  ",
            },
        )
        assert response.status_code == 422

    async def test_dhcp_needs_no_destination(self, authed_client: AsyncClient) -> None:
        response = await authed_client.post(
            "/api/v1/simulation/run",
            json={
                "document": routed_topology(),
                "sourceDeviceId": "pc1",
                "protocol": "dhcp",
            },
        )
        assert response.status_code == 200

    async def test_an_unreadable_device_config_names_the_device(
        self, authed_client: AsyncClient
    ) -> None:
        """Documents carry configs as free-form JSON, so this must not be a 500."""
        payload = routed_topology()
        payload["devices"][2]["config"]["dhcpPools"] = [
            {"name": "LAN", "network": "192.168.1.0", "subnetMask": "255.255.255.0"}
        ]

        response = await authed_client.post(
            "/api/v1/simulation/run",
            json={
                "document": payload,
                "sourceDeviceId": "pc1",
                "protocol": "ping",
                "destination": "10.0.0.10",
            },
        )

        assert response.status_code == 422
        assert "R1" in response.json()["error"]["message"]

    async def test_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/simulation/run",
            json={
                "document": routed_topology(),
                "sourceDeviceId": "pc1",
                "protocol": "ping",
                "destination": "10.0.0.10",
            },
        )
        assert response.status_code == 401


class TestCliPing:
    """`ping` at the CLI must run the real engine, not a canned response."""

    async def test_a_working_ping_prints_the_success_rate(self, authed_client: AsyncClient) -> None:
        response = await authed_client.post(
            "/api/v1/devices/cli",
            json={
                "document": routed_topology(),
                "deviceId": "r1",
                "command": "ping 10.0.0.10",
                "session": {"mode": "priv_exec", "hostname": "R1"},
                "config": next(
                    device["config"]
                    for device in routed_topology()["devices"]
                    if device["id"] == "r1"
                ),
            },
        )

        output = response.json()["output"]
        assert "!!!!!" in output
        assert "Success rate is 100 percent" in output

    async def test_a_broken_ping_explains_why(self, authed_client: AsyncClient) -> None:
        payload = routed_topology()
        payload["links"][3]["enabled"] = False

        response = await authed_client.post(
            "/api/v1/devices/cli",
            json={
                "document": payload,
                "deviceId": "r1",
                "command": "ping 10.0.0.10",
                "session": {"mode": "priv_exec", "hostname": "R1"},
                "config": next(
                    device["config"] for device in payload["devices"] if device["id"] == "r1"
                ),
            },
        )

        output = response.json()["output"]
        assert "....." in output
        assert "Success rate is 0 percent" in output
        assert "%" in output  # carries the diagnosis
