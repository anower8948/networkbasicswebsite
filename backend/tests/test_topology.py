"""Tests for the device catalogue, topology document, and editor endpoints."""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from app.models.enums import CableKind, DeviceKind
from app.schemas.topology import TopologyDocument
from app.services.device_catalog import CATALOG, cable_warning, recommended_cable, spec_for

TOPOLOGIES = "/api/v1/topologies"


def two_device_document(cable: str = "straight_through") -> dict[str, Any]:
    return {
        "devices": [
            {"id": "pc1", "kind": "pc", "name": "PC1", "position": {"x": 0, "y": 0}},
            {"id": "sw1", "kind": "switch", "name": "SW1", "position": {"x": 240, "y": 0}},
        ],
        "links": [
            {
                "id": "l1",
                "source": {"deviceId": "pc1", "interface": "Ethernet0"},
                "target": {"deviceId": "sw1", "interface": "FastEthernet0/1"},
                "cable": cable,
            }
        ],
        "groups": [],
        "viewport": {"x": 0, "y": 0, "zoom": 1},
    }


class TestDeviceCatalog:
    def test_covers_every_device_kind(self) -> None:
        assert set(CATALOG) == set(DeviceKind)

    def test_uses_real_cisco_interface_names(self) -> None:
        """Part 6's CLI will address these by name — they must be authentic."""
        router = spec_for(DeviceKind.ROUTER).interface_names()
        assert "GigabitEthernet0/0" in router
        assert "Serial0/0/0" in router

        switch = spec_for(DeviceKind.SWITCH).interface_names()
        assert "FastEthernet0/1" in switch
        assert "FastEthernet0/24" in switch
        assert "GigabitEthernet0/1" in switch

    def test_switch_has_a_realistic_port_count(self) -> None:
        # A 2960: 24 access ports, 2 uplinks, 1 console.
        assert len(spec_for(DeviceKind.SWITCH).interface_names()) == 27

    def test_interface_names_are_unique_per_device(self) -> None:
        for kind, spec in CATALOG.items():
            names = spec.interface_names()
            assert len(names) == len(set(names)), f"{kind.value} has duplicate interfaces"

    def test_every_device_has_at_least_one_connectable_port(self) -> None:
        for kind, spec in CATALOG.items():
            connectable = [i for i in spec.interfaces() if i["connectable"]]
            assert connectable, f"{kind.value} cannot be cabled to anything"

    def test_console_ports_are_not_connectable(self) -> None:
        """Console carries no traffic, so it must never be auto-assigned."""
        for entry in spec_for(DeviceKind.ROUTER).interfaces():
            if entry["name"] == "Console0":
                assert entry["connectable"] is False


class TestCableInference:
    @pytest.mark.parametrize(
        ("source", "source_if", "target", "target_if", "expected"),
        [
            # Unlike devices — straight-through.
            (
                DeviceKind.PC,
                "Ethernet0",
                DeviceKind.SWITCH,
                "FastEthernet0/1",
                CableKind.STRAIGHT_THROUGH,
            ),
            (
                DeviceKind.ROUTER,
                "GigabitEthernet0/0",
                DeviceKind.SWITCH,
                "FastEthernet0/1",
                CableKind.STRAIGHT_THROUGH,
            ),
            # Like devices — crossover.
            (
                DeviceKind.SWITCH,
                "GigabitEthernet0/1",
                DeviceKind.SWITCH,
                "GigabitEthernet0/2",
                CableKind.CROSSOVER,
            ),
            (DeviceKind.PC, "Ethernet0", DeviceKind.PC, "Ethernet0", CableKind.CROSSOVER),
            (
                DeviceKind.ROUTER,
                "GigabitEthernet0/0",
                DeviceKind.ROUTER,
                "GigabitEthernet0/1",
                CableKind.CROSSOVER,
            ),
            # Port type wins over device type.
            (DeviceKind.ROUTER, "Serial0/0/0", DeviceKind.ISP, "Serial0/0/0", CableKind.SERIAL),
            (
                DeviceKind.LAPTOP,
                "Wireless0",
                DeviceKind.ACCESS_POINT,
                "Wireless0",
                CableKind.WIRELESS,
            ),
        ],
    )
    def test_recommends_the_correct_cable(
        self,
        source: DeviceKind,
        source_if: str,
        target: DeviceKind,
        target_if: str,
        expected: CableKind,
    ) -> None:
        assert recommended_cable(source, source_if, target, target_if) is expected

    def test_the_right_cable_produces_no_warning(self) -> None:
        assert (
            cable_warning(
                DeviceKind.PC,
                "Ethernet0",
                DeviceKind.SWITCH,
                "FastEthernet0/1",
                CableKind.STRAIGHT_THROUGH,
            )
            is None
        )

    def test_the_wrong_cable_explains_why(self) -> None:
        message = cable_warning(
            DeviceKind.PC,
            "Ethernet0",
            DeviceKind.SWITCH,
            "FastEthernet0/1",
            CableKind.CROSSOVER,
        )
        assert message is not None
        assert "straight-through" in message

    def test_serial_mismatch_is_explained(self) -> None:
        message = cable_warning(
            DeviceKind.ROUTER,
            "Serial0/0/0",
            DeviceKind.ISP,
            "Serial0/0/0",
            CableKind.STRAIGHT_THROUGH,
        )
        assert message is not None
        assert "serial" in message.lower()


class TestDocumentValidation:
    def test_accepts_a_well_formed_document(self) -> None:
        document = TopologyDocument.model_validate(two_device_document())
        assert len(document.devices) == 2
        assert document.cable_issues() == []

    def test_rejects_a_link_to_an_unknown_device(self) -> None:
        payload = two_device_document()
        payload["links"][0]["source"]["deviceId"] = "ghost"

        with pytest.raises(ValidationError, match="unknown device"):
            TopologyDocument.model_validate(payload)

    def test_rejects_an_interface_the_device_does_not_have(self) -> None:
        payload = two_device_document()
        payload["links"][0]["source"]["interface"] = "GigabitEthernet9/9"

        with pytest.raises(ValidationError, match="no interface"):
            TopologyDocument.model_validate(payload)

    def test_rejects_two_cables_in_one_port(self) -> None:
        """The constraint that makes a saved topology physically buildable."""
        payload = two_device_document()
        payload["devices"].append(
            {"id": "pc2", "kind": "pc", "name": "PC2", "position": {"x": 0, "y": 120}}
        )
        payload["links"].append(
            {
                "id": "l2",
                "source": {"deviceId": "pc2", "interface": "Ethernet0"},
                # Already carrying l1.
                "target": {"deviceId": "sw1", "interface": "FastEthernet0/1"},
                "cable": "straight_through",
            }
        )

        with pytest.raises(ValidationError, match="already carries"):
            TopologyDocument.model_validate(payload)

    def test_rejects_duplicate_device_ids(self) -> None:
        payload = two_device_document()
        payload["devices"][1]["id"] = "pc1"
        payload["links"] = []

        with pytest.raises(ValidationError, match="Duplicate device id"):
            TopologyDocument.model_validate(payload)

    def test_rejects_an_unknown_group_reference(self) -> None:
        payload = two_device_document()
        payload["devices"][0]["groupId"] = "missing"

        with pytest.raises(ValidationError, match="unknown group"):
            TopologyDocument.model_validate(payload)

    def test_rejects_unknown_keys(self) -> None:
        """Round-tripping must not silently drop data a client sent."""
        payload = two_device_document()
        payload["unexpected"] = True

        with pytest.raises(ValidationError):
            TopologyDocument.model_validate(payload)

    def test_a_miscabled_link_saves_but_warns(self) -> None:
        """Learners are allowed to make the classic mistake and see why."""
        document = TopologyDocument.model_validate(two_device_document(cable="crossover"))

        issues = document.cable_issues()
        assert len(issues) == 1
        assert "straight-through" in issues[0].message


class TestTopologyEndpoints:
    async def test_device_catalog_is_public(self, client: AsyncClient) -> None:
        response = await client.get(f"{TOPOLOGIES}/device-catalog")

        assert response.status_code == 200
        catalog = response.json()
        assert len(catalog) == len(DeviceKind)
        router = next(item for item in catalog if item["kind"] == "router")
        assert router["hasCli"] is True
        assert any(i["name"] == "GigabitEthernet0/0" for i in router["interfaces"])

    async def test_creates_and_loads_a_topology(self, authed_client: AsyncClient) -> None:
        created = await authed_client.post(
            TOPOLOGIES, json={"name": "Home network", "document": two_device_document()}
        )

        assert created.status_code == 201
        body = created.json()
        assert body["name"] == "Home network"
        assert body["deviceCount"] == 2

        loaded = await authed_client.get(f"{TOPOLOGIES}/{body['id']}")
        assert loaded.status_code == 200
        assert len(loaded.json()["document"]["devices"]) == 2

    async def test_device_count_is_derived_not_trusted(self, authed_client: AsyncClient) -> None:
        """The summary count must always match the document it summarises."""
        created = await authed_client.post(
            TOPOLOGIES, json={"name": "Counted", "document": two_device_document()}
        )
        topology_id = created.json()["id"]

        document = two_device_document()
        document["devices"].append(
            {"id": "pc9", "kind": "pc", "name": "PC9", "position": {"x": 9, "y": 9}}
        )
        updated = await authed_client.patch(
            f"{TOPOLOGIES}/{topology_id}", json={"document": document}
        )

        assert updated.json()["deviceCount"] == 3

    async def test_saving_an_invalid_document_is_rejected(self, authed_client: AsyncClient) -> None:
        payload = two_device_document()
        payload["links"][0]["target"]["interface"] = "NotAPort0/1"

        response = await authed_client.post(
            TOPOLOGIES, json={"name": "Broken", "document": payload}
        )
        assert response.status_code == 422

    async def test_reports_cabling_warnings_on_read(self, authed_client: AsyncClient) -> None:
        created = await authed_client.post(
            TOPOLOGIES,
            json={"name": "Miscabled", "document": two_device_document(cable="crossover")},
        )

        issues = created.json()["issues"]
        assert len(issues) == 1
        assert issues[0]["linkId"] == "l1"

    async def test_lists_only_your_own_topologies(
        self, client: AsyncClient, user_payload: dict[str, str]
    ) -> None:
        owner = await client.post("/api/v1/auth/register", json=user_payload)
        client.headers["Authorization"] = f"Bearer {owner.json()['accessToken']}"
        await client.post(TOPOLOGIES, json={"name": "Mine", "document": two_device_document()})

        other = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "other@example.com",
                "username": "other",
                "password": "OtherPass2024",
            },
        )
        client.headers["Authorization"] = f"Bearer {other.json()['accessToken']}"

        listing = await client.get(TOPOLOGIES)
        assert listing.json()["total"] == 0

    async def test_cannot_load_someone_elses_private_topology(
        self, client: AsyncClient, user_payload: dict[str, str]
    ) -> None:
        owner = await client.post("/api/v1/auth/register", json=user_payload)
        client.headers["Authorization"] = f"Bearer {owner.json()['accessToken']}"
        created = await client.post(
            TOPOLOGIES, json={"name": "Private", "document": two_device_document()}
        )
        topology_id = created.json()["id"]

        attacker = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "attacker@example.com",
                "username": "attacker",
                "password": "AttackerPass24",
            },
        )
        client.headers["Authorization"] = f"Bearer {attacker.json()['accessToken']}"

        # 404, not 403 — this endpoint must not confirm the id exists.
        assert (await client.get(f"{TOPOLOGIES}/{topology_id}")).status_code == 404
        assert (await client.delete(f"{TOPOLOGIES}/{topology_id}")).status_code == 404
        assert (
            await client.patch(f"{TOPOLOGIES}/{topology_id}", json={"name": "Stolen"})
        ).status_code == 404

    async def test_deletes_a_topology(self, authed_client: AsyncClient) -> None:
        created = await authed_client.post(
            TOPOLOGIES, json={"name": "Temporary", "document": two_device_document()}
        )
        topology_id = created.json()["id"]

        assert (await authed_client.delete(f"{TOPOLOGIES}/{topology_id}")).status_code == 200
        assert (await authed_client.get(f"{TOPOLOGIES}/{topology_id}")).status_code == 404

    async def test_duplicating_makes_an_independent_copy(self, authed_client: AsyncClient) -> None:
        created = await authed_client.post(
            TOPOLOGIES, json={"name": "Original", "document": two_device_document()}
        )
        original_id = created.json()["id"]

        copy = await authed_client.post(f"{TOPOLOGIES}/{original_id}/duplicate")
        assert copy.status_code == 201
        assert copy.json()["id"] != original_id
        assert copy.json()["name"] == "Original (copy)"

        # Editing the copy must not touch the original.
        await authed_client.patch(f"{TOPOLOGIES}/{copy.json()['id']}", json={"name": "Changed"})
        assert (await authed_client.get(f"{TOPOLOGIES}/{original_id}")).json()["name"] == "Original"

    async def test_export_import_round_trip(self, authed_client: AsyncClient) -> None:
        created = await authed_client.post(
            TOPOLOGIES, json={"name": "Exportable", "document": two_device_document()}
        )
        exported = await authed_client.get(f"{TOPOLOGIES}/{created.json()['id']}/export")

        assert exported.status_code == 200
        payload = exported.json()
        assert payload["format"] == "network-learning-platform/topology"
        # An export describes a network, not a database row.
        assert "id" not in payload
        assert "ownerId" not in payload

        imported = await authed_client.post(
            f"{TOPOLOGIES}/import",
            json={"name": "Re-imported", "document": payload["document"]},
        )
        assert imported.status_code == 201
        assert imported.json()["deviceCount"] == 2

    async def test_importing_a_corrupt_file_is_rejected(self, authed_client: AsyncClient) -> None:
        broken = two_device_document()
        broken["links"][0]["source"]["deviceId"] = "does-not-exist"

        response = await authed_client.post(
            f"{TOPOLOGIES}/import", json={"name": "Corrupt", "document": broken}
        )
        assert response.status_code == 422

    async def test_topologies_require_authentication(self, client: AsyncClient) -> None:
        assert (await client.get(TOPOLOGIES)).status_code == 401
        assert (
            await client.post(TOPOLOGIES, json={"name": "x", "document": {}})
        ).status_code == 401


class TestLinkSuggestion:
    async def test_picks_free_ports_and_infers_the_cable(self, authed_client: AsyncClient) -> None:
        document = two_device_document()
        document["links"] = []

        response = await authed_client.post(
            f"{TOPOLOGIES}/suggest-link?source=pc1&target=sw1", json=document
        )

        assert response.status_code == 200
        body = response.json()
        assert body["sourceInterface"] == "Ethernet0"
        assert body["targetInterface"] == "FastEthernet0/1"
        assert body["cable"] == "straight_through"
        assert body["warning"] is None

    async def test_skips_ports_already_carrying_a_link(self, authed_client: AsyncClient) -> None:
        """FastEthernet0/1 is taken, so the next suggestion must be 0/2."""
        document = two_device_document()
        document["devices"].append(
            {"id": "pc2", "kind": "pc", "name": "PC2", "position": {"x": 0, "y": 120}}
        )

        response = await authed_client.post(
            f"{TOPOLOGIES}/suggest-link?source=pc2&target=sw1", json=document
        )

        assert response.json()["targetInterface"] == "FastEthernet0/2"

    async def test_warns_when_an_explicit_cable_is_wrong(self, authed_client: AsyncClient) -> None:
        document = two_device_document()
        document["links"] = []

        response = await authed_client.post(
            f"{TOPOLOGIES}/suggest-link?source=pc1&target=sw1&cable=crossover", json=document
        )

        body = response.json()
        assert body["cable"] == "crossover"
        assert "straight-through" in body["warning"]

    async def test_reports_when_a_device_is_full(self, authed_client: AsyncClient) -> None:
        """A PC has one NIC; a second cable has nowhere to go."""
        document = two_device_document()
        document["devices"].append(
            {"id": "sw2", "kind": "switch", "name": "SW2", "position": {"x": 480, "y": 0}}
        )

        response = await authed_client.post(
            f"{TOPOLOGIES}/suggest-link?source=pc1&target=sw2", json=document
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "no_free_interface"
