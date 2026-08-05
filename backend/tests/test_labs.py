"""Tests for lab grading, fault injection, and delivery.

Two things are being defended here beyond "the code runs":

* **The seeded labs are solvable and the troubleshooting lab is genuinely
  broken.** A lab whose rules cannot all pass is worse than no lab.
* **Nothing that gives the answer away reaches the client.** Grading rules and
  fault injections must never appear in a learner-facing payload.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest
from httpx import AsyncClient
from pydantic import TypeAdapter

from app.schemas.lab import FaultInjection, GradingRule, LabObjective, LabWrite
from app.schemas.topology import TopologyDocument
from app.seeds.lab_content import (
    BROKEN_OFFICE,
    FIRST_LAN,
    LABS,
    TWO_SUBNETS,
    VLAN_SEGMENTATION,
)
from app.services.fault_injection import apply_faults
from app.services.grading import LabGrader

_RULES = TypeAdapter(list[GradingRule])
_FAULTS = TypeAdapter(list[FaultInjection])


def authored(data: dict[str, Any]) -> LabWrite:
    return LabWrite.model_validate({**data, "isPublished": True})


def grade(document: TopologyDocument, lab: LabWrite) -> Any:
    return LabGrader(document).grade(lab.grading_rules, lab.objectives)


def device(document: dict[str, Any], name: str) -> dict[str, Any]:
    return next(item for item in document["devices"] if item["name"] == name)


def set_interface(document: dict[str, Any], name: str, interface: str, **values: Any) -> None:
    config = device(document, name).setdefault("config", {})
    interfaces = config.setdefault("interfaces", {})
    interfaces.setdefault(interface, {}).update(values)


def addressed(ip: str, mask: str = "255.255.255.0") -> dict[str, Any]:
    return {"ipAddress": ip, "subnetMask": mask, "enabled": True}


class TestAuthoredLabsAreValid:
    """Every shipped lab must survive validation and be solvable."""

    @pytest.mark.parametrize("data", LABS, ids=lambda item: str(item["slug"]))
    def test_a_lab_validates(self, data: dict[str, Any]) -> None:
        lab = authored(data)
        assert lab.grading_rules, "a lab with no rules cannot be graded"
        assert lab.objectives, "a lab with no objectives has nothing to show the student"

    @pytest.mark.parametrize("data", LABS, ids=lambda item: str(item["slug"]))
    def test_every_rule_ties_to_a_real_objective(self, data: dict[str, Any]) -> None:
        """Otherwise a failed rule ticks nothing and the student sees no reason."""
        lab = authored(data)
        objective_ids = {item.id for item in lab.objectives}
        for rule in lab.grading_rules:
            assert rule.objective_id in objective_ids, f"{rule.id} points at nothing"

    @pytest.mark.parametrize("data", LABS, ids=lambda item: str(item["slug"]))
    def test_the_points_add_up_to_a_passable_score(self, data: dict[str, Any]) -> None:
        lab = authored(data)
        total = sum(rule.points for rule in lab.grading_rules)
        assert total > 0
        # A lab whose rules cannot reach its own passing score is unpassable.
        assert lab.passing_score <= 100


class TestTroubleshootingLabIntegrity:
    """The authored network must work, and the faults must actually break it."""

    def test_the_authored_network_passes_its_own_rules(self) -> None:
        lab = authored(BROKEN_OFFICE)
        report = grade(lab.initial_topology, lab)
        assert report.score_percent == 100.0, [
            (item.rule_id, item.detail) for item in report.results if not item.passed
        ]

    def test_injecting_the_faults_breaks_it(self) -> None:
        lab = authored(BROKEN_OFFICE)
        broken = apply_faults(lab.initial_topology, lab.fault_injections)

        report = grade(broken, lab)
        assert report.score_percent < lab.passing_score

    def test_the_failure_names_the_actual_fault(self) -> None:
        """The simulator's diagnosis is the feedback, so it must be specific."""
        lab = authored(BROKEN_OFFICE)
        broken = apply_faults(lab.initial_topology, lab.fault_injections)

        report = grade(broken, lab)
        ping = next(item for item in report.results if item.rule_id == "pc1-reaches-server")
        assert not ping.passed
        assert "192.168.1.254" in (ping.detail or "")

    def test_fixing_both_faults_passes_the_lab(self) -> None:
        lab = authored(BROKEN_OFFICE)
        broken = apply_faults(lab.initial_topology, lab.fault_injections).model_dump(
            mode="json", by_alias=True
        )

        device(broken, "PC1")["config"]["defaultGateway"] = "192.168.1.1"
        set_interface(broken, "R1", "GigabitEthernet0/1", enabled=True)

        report = grade(TopologyDocument.model_validate(broken), lab)
        assert report.score_percent == 100.0

    def test_every_fault_explains_itself(self) -> None:
        """The post-mortem after a pass is the point of the exercise."""
        lab = authored(BROKEN_OFFICE)
        for fault in lab.fault_injections:
            assert fault.explanation, f"{fault.id} has no explanation"


class TestFaultInjection:
    def test_it_does_not_mutate_the_authored_topology(self) -> None:
        """The intact network is reused for every attempt; breaking it once
        would break it for everyone."""
        lab = authored(BROKEN_OFFICE)
        before = lab.initial_topology.model_dump(mode="json", by_alias=True)

        apply_faults(lab.initial_topology, lab.fault_injections)

        assert lab.initial_topology.model_dump(mode="json", by_alias=True) == before

    def test_a_fault_naming_a_missing_device_is_skipped_not_raised(self) -> None:
        """A stale fault must not make the whole lab unopenable."""
        lab = authored(BROKEN_OFFICE)
        faults = _FAULTS.validate_python(
            [{"id": "ghost", "type": "shutdown_interface", "device": "NOPE", "interface": "Gi0/0"}]
        )

        result = apply_faults(lab.initial_topology, faults)

        assert result is not None

    def test_disabling_a_link_cuts_the_path(self) -> None:
        lab = authored(BROKEN_OFFICE)
        faults = _FAULTS.validate_python(
            [{"id": "cut", "type": "disable_link", "source": "SW1", "destination": "R1"}]
        )

        broken = apply_faults(lab.initial_topology, faults)

        link = next(
            item
            for item in broken.links
            if {item.source.device_id, item.target.device_id} == {"sw1", "r1"}
        )
        assert link.enabled is False

    def test_a_wrong_cable_is_applied_as_a_cable_type(self) -> None:
        lab = authored(BROKEN_OFFICE)
        faults = _FAULTS.validate_python(
            [
                {
                    "id": "miscable",
                    "type": "wrong_cable",
                    "source": "PC1",
                    "destination": "SW1",
                    "cable": "crossover",
                }
            ]
        )

        broken = apply_faults(lab.initial_topology, faults)

        link = next(item for item in broken.links if item.id == "l1")
        assert link.cable.value == "crossover"


class TestSolvingTheBuildLabs:
    """Each build lab starts unsolved and reaches 100 when done properly."""

    def test_the_first_lan_starts_unsolved(self) -> None:
        lab = authored(FIRST_LAN)
        assert grade(lab.initial_topology, lab).score_percent == 0.0

    def test_the_first_lan_can_be_solved(self) -> None:
        lab = authored(FIRST_LAN)
        document = lab.initial_topology.model_dump(mode="json", by_alias=True)

        set_interface(document, "PC1", "Ethernet0", **addressed("192.168.10.11"))
        set_interface(document, "PC2", "Ethernet0", **addressed("192.168.10.12"))

        report = grade(TopologyDocument.model_validate(document), lab)
        assert report.score_percent == 100.0

    def test_matching_addresses_with_mismatched_masks_still_fails(self) -> None:
        """The classic subnetting error: right addresses, wrong mask."""
        lab = authored(FIRST_LAN)
        document = lab.initial_topology.model_dump(mode="json", by_alias=True)

        set_interface(document, "PC1", "Ethernet0", **addressed("192.168.10.11"))
        set_interface(document, "PC2", "Ethernet0", **addressed("192.168.10.12", "255.255.255.128"))

        report = grade(TopologyDocument.model_validate(document), lab)
        assert report.score_percent < 100.0

    def test_the_routing_lab_can_be_solved(self) -> None:
        lab = authored(TWO_SUBNETS)
        document = lab.initial_topology.model_dump(mode="json", by_alias=True)

        set_interface(document, "R1", "GigabitEthernet0/0", **addressed("192.168.1.1"))
        set_interface(document, "R1", "GigabitEthernet0/1", **addressed("10.0.0.1"))
        device(document, "PC1")["config"]["defaultGateway"] = "192.168.1.1"
        device(document, "SRV1")["config"]["defaultGateway"] = "10.0.0.1"

        report = grade(TopologyDocument.model_validate(document), lab)
        assert report.score_percent == 100.0

    def test_leaving_a_router_interface_shut_fails_with_that_reason(self) -> None:
        """The single most common mistake in this lab."""
        lab = authored(TWO_SUBNETS)
        document = lab.initial_topology.model_dump(mode="json", by_alias=True)

        set_interface(
            document,
            "R1",
            "GigabitEthernet0/0",
            ipAddress="192.168.1.1",
            subnetMask="255.255.255.0",
            enabled=False,
        )
        set_interface(document, "R1", "GigabitEthernet0/1", **addressed("10.0.0.1"))
        device(document, "PC1")["config"]["defaultGateway"] = "192.168.1.1"
        device(document, "SRV1")["config"]["defaultGateway"] = "10.0.0.1"

        report = grade(TopologyDocument.model_validate(document), lab)
        failed = next(item for item in report.results if item.rule_id == "r1-gi00")
        assert "no shutdown" in (failed.detail or "")

    def test_the_vlan_lab_can_be_solved(self) -> None:
        lab = authored(VLAN_SEGMENTATION)
        document = lab.initial_topology.model_dump(mode="json", by_alias=True)

        for interface, vlan in [
            ("FastEthernet0/1", 10),
            ("FastEthernet0/2", 10),
            ("FastEthernet0/3", 20),
        ]:
            set_interface(document, "SW1", interface, switchportMode="access", accessVlan=vlan)

        report = grade(TopologyDocument.model_validate(document), lab)
        assert report.score_percent == 100.0

    def test_putting_everyone_in_one_vlan_fails_the_isolation_rule(self) -> None:
        """The reason `no_ping` exists: connectivity alone is not the goal."""
        lab = authored(VLAN_SEGMENTATION)
        document = lab.initial_topology.model_dump(mode="json", by_alias=True)

        for interface in ("FastEthernet0/1", "FastEthernet0/2", "FastEthernet0/3"):
            set_interface(document, "SW1", interface, switchportMode="access", accessVlan=10)

        report = grade(TopologyDocument.model_validate(document), lab)
        isolation = next(item for item in report.results if item.rule_id == "guest-isolated")
        assert not isolation.passed
        assert "still reaches" in (isolation.detail or "")


class TestGradingRules:
    """Rule-level behaviour, checked away from any particular lab."""

    @staticmethod
    def two_host_document() -> dict[str, Any]:
        return {
            "devices": [
                {
                    "id": "a",
                    "kind": "pc",
                    "name": "A",
                    "position": {"x": 0, "y": 0},
                    "config": {
                        "hostname": "alpha",
                        "interfaces": {"Ethernet0": addressed("10.1.1.5")},
                        "defaultGateway": "10.1.1.1",
                    },
                },
                {
                    "id": "sw",
                    "kind": "switch",
                    "name": "SW",
                    "position": {"x": 1, "y": 0},
                    "config": {},
                },
                {
                    "id": "b",
                    "kind": "pc",
                    "name": "B",
                    "position": {"x": 2, "y": 0},
                    "config": {"interfaces": {"Ethernet0": addressed("10.1.1.6")}},
                },
            ],
            "links": [
                {
                    "id": "l1",
                    "source": {"deviceId": "a", "interface": "Ethernet0"},
                    "target": {"deviceId": "sw", "interface": "FastEthernet0/1"},
                    "cable": "straight_through",
                },
                {
                    "id": "l2",
                    "source": {"deviceId": "sw", "interface": "FastEthernet0/2"},
                    "target": {"deviceId": "b", "interface": "Ethernet0"},
                    "cable": "straight_through",
                },
            ],
            "groups": [],
            "viewport": {"x": 0, "y": 0, "zoom": 1},
        }

    def check(self, rule: dict[str, Any], document: dict[str, Any] | None = None) -> Any:
        payload = document or self.two_host_document()
        grader = LabGrader(TopologyDocument.model_validate(payload))
        report = grader.grade(_RULES.validate_python([rule]), [])
        return report.results[0]

    def test_devices_are_addressed_by_name_case_insensitively(self) -> None:
        result = self.check({"id": "r", "type": "hostname", "device": "a", "hostname": "ALPHA"})
        assert result.passed

    def test_a_rule_naming_a_missing_device_says_so(self) -> None:
        result = self.check({"id": "r", "type": "hostname", "device": "Z", "hostname": "z"})
        assert not result.passed
        assert "no device called Z" in (result.detail or "")

    def test_in_subnet_accepts_any_host_address_in_range(self) -> None:
        result = self.check(
            {"id": "r", "type": "in_subnet", "device": "B", "network": "10.1.1.0/24"}
        )
        assert result.passed

    def test_in_subnet_rejects_an_address_outside_it(self) -> None:
        result = self.check(
            {"id": "r", "type": "in_subnet", "device": "B", "network": "192.168.0.0/24"}
        )
        assert not result.passed
        assert "outside" in (result.detail or "")

    def test_device_count_counts_by_kind(self) -> None:
        result = self.check({"id": "r", "type": "device_count", "kind": "pc", "minimum": 2})
        assert result.passed

    def test_device_count_reports_what_was_found(self) -> None:
        result = self.check({"id": "r", "type": "device_count", "kind": "router", "minimum": 1})
        assert not result.passed
        assert "There are 0" in (result.detail or "")

    def test_a_link_rule_passes_for_a_working_cable(self) -> None:
        result = self.check({"id": "r", "type": "link", "source": "A", "destination": "SW"})
        assert result.passed

    def test_a_disabled_link_fails_differently_from_a_missing_one(self) -> None:
        document = self.two_host_document()
        document["links"][0]["enabled"] = False

        result = self.check(
            {"id": "r", "type": "link", "source": "A", "destination": "SW"}, document
        )

        assert not result.passed
        assert "disabled" in (result.detail or "")

    def test_a_missing_cable_says_there_is_none(self) -> None:
        result = self.check({"id": "r", "type": "link", "source": "A", "destination": "B"})
        assert not result.passed
        assert "no cable" in (result.detail or "")

    def test_an_author_message_is_added_to_a_failure(self) -> None:
        result = self.check(
            {
                "id": "r",
                "type": "hostname",
                "device": "B",
                "hostname": "beta",
                "message": "Name your devices.",
            }
        )
        assert not result.passed
        assert "Name your devices." in (result.detail or "")

    def test_a_passing_rule_does_not_show_the_scolding_message(self) -> None:
        result = self.check(
            {
                "id": "r",
                "type": "hostname",
                "device": "A",
                "hostname": "alpha",
                "message": "Name your devices.",
            }
        )
        assert result.passed
        assert "Name your devices." not in (result.detail or "")

    def test_an_objective_with_no_rules_does_not_fail_the_student(self) -> None:
        grader = LabGrader(TopologyDocument.model_validate(self.two_host_document()))
        report = grader.grade(
            _RULES.validate_python([]),
            [LabObjective(id="read-the-brief", title="Read the brief", points=0)],
        )
        assert report.objectives[0].passed

    def test_an_objective_fails_when_any_of_its_rules_fails(self) -> None:
        grader = LabGrader(TopologyDocument.model_validate(self.two_host_document()))
        report = grader.grade(
            _RULES.validate_python(
                [
                    {
                        "id": "ok",
                        "type": "hostname",
                        "objectiveId": "naming",
                        "device": "A",
                        "hostname": "alpha",
                    },
                    {
                        "id": "bad",
                        "type": "hostname",
                        "objectiveId": "naming",
                        "device": "B",
                        "hostname": "beta",
                    },
                ]
            ),
            [LabObjective(id="naming", title="Name everything", points=10)],
        )
        assert not report.objectives[0].passed


@pytest.mark.usefixtures("seeded_catalog")
class TestLabEndpoints:
    async def test_the_library_lists_published_labs(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/labs")

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == len(LABS)

    async def test_a_lab_briefing_never_includes_the_answers(self, client: AsyncClient) -> None:
        """The whole point of the learner-facing projection."""
        response = await client.get("/api/v1/labs/the-office-cannot-reach-the-server")

        assert response.status_code == 200
        body = response.json()
        assert "gradingRules" not in body
        assert "faultInjections" not in body
        assert "192.168.1.254" not in response.text

    async def test_starting_an_attempt_returns_the_broken_topology(
        self, authed_client: AsyncClient
    ) -> None:
        response = await authed_client.post(
            "/api/v1/labs/the-office-cannot-reach-the-server/attempts"
        )

        assert response.status_code == 200
        document = response.json()["workingTopology"]
        pc1 = next(item for item in document["devices"] if item["name"] == "PC1")
        assert pc1["config"]["defaultGateway"] == "192.168.1.254"

    async def test_reopening_a_lab_resumes_the_same_attempt(
        self, authed_client: AsyncClient
    ) -> None:
        """A lab holds half an hour of work; a refresh must not discard it."""
        first = await authed_client.post("/api/v1/labs/your-first-lan/attempts")
        second = await authed_client.post("/api/v1/labs/your-first-lan/attempts")

        assert first.json()["id"] == second.json()["id"]

    async def test_saving_and_checking_reports_progress(self, authed_client: AsyncClient) -> None:
        started = await authed_client.post("/api/v1/labs/your-first-lan/attempts")
        attempt_id = started.json()["id"]
        document = copy.deepcopy(started.json()["workingTopology"])
        set_interface(document, "PC1", "Ethernet0", **addressed("192.168.10.11"))

        saved = await authed_client.put(
            f"/api/v1/labs/attempts/{attempt_id}/topology",
            json={"document": document, "timeSpentSeconds": 90},
        )
        assert saved.status_code == 200

        checked = await authed_client.post(f"/api/v1/labs/attempts/{attempt_id}/check")

        assert checked.status_code == 200
        body = checked.json()
        assert not body["passed"]
        assert body["scorePercent"] > 0
        # Checking must not close the attempt.
        assert body["status"] == "in_progress"

    async def test_submitting_a_solved_lab_passes_and_pays_xp(
        self, authed_client: AsyncClient
    ) -> None:
        started = await authed_client.post("/api/v1/labs/your-first-lan/attempts")
        attempt_id = started.json()["id"]
        document = copy.deepcopy(started.json()["workingTopology"])
        set_interface(document, "PC1", "Ethernet0", **addressed("192.168.10.11"))
        set_interface(document, "PC2", "Ethernet0", **addressed("192.168.10.12"))

        await authed_client.put(
            f"/api/v1/labs/attempts/{attempt_id}/topology", json={"document": document}
        )
        response = await authed_client.post(f"/api/v1/labs/attempts/{attempt_id}/submit")

        assert response.status_code == 200
        body = response.json()
        assert body["passed"]
        assert body["scorePercent"] == 100.0
        assert body["status"] == "passed"
        assert body["xpAwarded"] == FIRST_LAN["xp_reward"]

    async def test_passing_the_same_lab_twice_pays_once(self, authed_client: AsyncClient) -> None:
        async def solve_and_submit() -> dict[str, Any]:
            started = await authed_client.post("/api/v1/labs/your-first-lan/attempts")
            attempt_id = started.json()["id"]
            document = copy.deepcopy(started.json()["workingTopology"])
            set_interface(document, "PC1", "Ethernet0", **addressed("192.168.10.11"))
            set_interface(document, "PC2", "Ethernet0", **addressed("192.168.10.12"))
            await authed_client.put(
                f"/api/v1/labs/attempts/{attempt_id}/topology", json={"document": document}
            )
            result = await authed_client.post(f"/api/v1/labs/attempts/{attempt_id}/submit")
            return dict(result.json())

        first = await solve_and_submit()
        second = await solve_and_submit()

        assert first["xpAwarded"] > 0
        assert second["xpAwarded"] == 0

    async def test_the_faults_are_revealed_only_after_passing(
        self, authed_client: AsyncClient
    ) -> None:
        slug = "the-office-cannot-reach-the-server"
        started = await authed_client.post(f"/api/v1/labs/{slug}/attempts")
        attempt_id = started.json()["id"]
        document = copy.deepcopy(started.json()["workingTopology"])

        # Checking while still broken reveals nothing.
        mid = await authed_client.post(f"/api/v1/labs/attempts/{attempt_id}/check")
        assert mid.json()["faultExplanations"] == []

        device(document, "PC1")["config"]["defaultGateway"] = "192.168.1.1"
        set_interface(document, "R1", "GigabitEthernet0/1", enabled=True)
        await authed_client.put(
            f"/api/v1/labs/attempts/{attempt_id}/topology", json={"document": document}
        )
        done = await authed_client.post(f"/api/v1/labs/attempts/{attempt_id}/submit")

        assert done.json()["passed"]
        assert len(done.json()["faultExplanations"]) == 2

    async def test_a_hint_is_counted(self, authed_client: AsyncClient) -> None:
        started = await authed_client.post("/api/v1/labs/your-first-lan/attempts")
        attempt_id = started.json()["id"]

        response = await authed_client.post(
            f"/api/v1/labs/attempts/{attempt_id}/hint",
            json={"objectiveId": "address-pc1"},
        )

        assert response.status_code == 200
        assert response.json()["hint"]
        assert response.json()["hintsUsed"] == 1

    async def test_submitting_twice_is_rejected(self, authed_client: AsyncClient) -> None:
        started = await authed_client.post("/api/v1/labs/your-first-lan/attempts")
        attempt_id = started.json()["id"]

        await authed_client.post(f"/api/v1/labs/attempts/{attempt_id}/submit")
        again = await authed_client.post(f"/api/v1/labs/attempts/{attempt_id}/submit")

        assert again.status_code == 409

    async def test_another_learners_attempt_is_not_reachable(
        self, authed_client: AsyncClient, client: AsyncClient
    ) -> None:
        started = await authed_client.post("/api/v1/labs/your-first-lan/attempts")
        attempt_id = started.json()["id"]

        intruder = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "other@example.com",
                "username": "other",
                "password": "Subnetting2024",
                "fullName": "Other",
            },
        )
        token = intruder.json()["accessToken"]

        response = await client.post(
            f"/api/v1/labs/attempts/{attempt_id}/check",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 404

    async def test_starting_an_attempt_requires_a_user(self, client: AsyncClient) -> None:
        response = await client.post("/api/v1/labs/your-first-lan/attempts")
        assert response.status_code == 401

    async def test_an_unknown_lab_is_404(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/labs/no-such-lab")
        assert response.status_code == 404
