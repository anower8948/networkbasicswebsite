"""Lab authoring and delivery schemas.

Two discriminated unions carry the whole of Part 8's authoring model:

* **Grading rules** — declarative assertions about a finished network. The
  grader evaluates them against the learner's document, using the Part 7
  simulation engine for anything that requires traffic to actually flow.
* **Fault injections** — deliberate breakages applied to a troubleshooting
  lab's starting topology.

Both are declarative on purpose. An author writes a lab as data, not code, so
labs can be seeded, edited by instructors, and validated at write time rather
than discovered broken by a student. Adding a rule type means adding a model
here and a branch in `app.services.grading`; nothing else changes.

**Neither the rules nor the faults are ever sent to a student.** `LabDetail` is
the learner-facing projection and carries neither, for the same reason the quiz
payload omits its answer key: the answer must not be in the network tab.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AttemptStatus, Difficulty, LabKind, ScenarioType
from app.schemas.common import APIModel
from app.schemas.gamification import AchievementRead
from app.schemas.topology import TopologyDocument


class AuthoringModel(BaseModel):
    """Authoring documents are stored verbatim, so typos must not survive."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


# --------------------------------------------------------------------------- #
# Objectives
# --------------------------------------------------------------------------- #
class LabObjective(AuthoringModel):
    """One checkpoint on the student's task list.

    An objective is what the student *reads*; a grading rule is what the server
    *checks*. They are joined by `id` so a failed rule can tick the right box,
    but they stay separate because one objective ("give every host an address")
    is often several rules.
    """

    id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=200)
    hint: str | None = Field(default=None, max_length=600)
    points: int = Field(default=10, ge=0, le=100)


# --------------------------------------------------------------------------- #
# Grading rules
# --------------------------------------------------------------------------- #
class RuleBase(AuthoringModel):
    id: str = Field(min_length=1, max_length=64)
    # Ties the rule to a `LabObjective.id`, so results tick the student's list.
    objective_id: str | None = Field(default=None, max_length=64, alias="objectiveId")
    points: int = Field(default=10, ge=0, le=100)
    # Shown when the rule fails. Optional: each rule can describe itself.
    message: str | None = Field(default=None, max_length=400)


class PingRule(RuleBase):
    """Traffic must flow from one device to an address or device name."""

    type: Literal["ping"] = "ping"
    source: str = Field(min_length=1, max_length=64)
    destination: str = Field(min_length=1, max_length=64)


class NoPingRule(RuleBase):
    """Traffic must *not* flow — the assertion segmentation labs are built on.

    Without this, a student can pass a VLAN or ACL lab by connecting everything
    to everything: the reachability rules would all be green.
    """

    type: Literal["no_ping"] = "no_ping"
    source: str = Field(min_length=1, max_length=64)
    destination: str = Field(min_length=1, max_length=64)


class DnsRule(RuleBase):
    type: Literal["dns"] = "dns"
    source: str = Field(min_length=1, max_length=64)
    hostname: str = Field(min_length=1, max_length=128)


class PortRule(RuleBase):
    """A TCP service must be reachable."""

    type: Literal["port"] = "port"
    source: str = Field(min_length=1, max_length=64)
    destination: str = Field(min_length=1, max_length=64)
    port: int = Field(ge=1, le=65535)


class DhcpLeaseRule(RuleBase):
    """A client must be able to obtain an address from a pool."""

    type: Literal["dhcp_lease"] = "dhcp_lease"
    source: str = Field(min_length=1, max_length=64)


class InterfaceAddressRule(RuleBase):
    """A specific interface must carry a specific address."""

    type: Literal["interface_address"] = "interface_address"
    device: str = Field(min_length=1, max_length=64)
    interface: str = Field(min_length=1, max_length=64)
    address: str | None = None
    mask: str | None = None
    # None means "do not care"; True is how a lab asserts `no shutdown`.
    enabled: bool | None = None


class InSubnetRule(RuleBase):
    """An interface's address must fall inside a given subnet.

    Used where the exact host address is the student's choice but the subnet is
    not — most addressing labs, in other words.
    """

    type: Literal["in_subnet"] = "in_subnet"
    device: str = Field(min_length=1, max_length=64)
    interface: str | None = Field(default=None, max_length=64)
    network: str = Field(min_length=1, max_length=32)


class GatewayRule(RuleBase):
    type: Literal["gateway"] = "gateway"
    device: str = Field(min_length=1, max_length=64)
    gateway: str = Field(min_length=1, max_length=45)


class HostnameRule(RuleBase):
    type: Literal["hostname"] = "hostname"
    device: str = Field(min_length=1, max_length=64)
    hostname: str = Field(min_length=1, max_length=63)


class StaticRouteRule(RuleBase):
    type: Literal["static_route"] = "static_route"
    device: str = Field(min_length=1, max_length=64)
    network: str = Field(min_length=1, max_length=32)
    next_hop: str | None = Field(default=None, max_length=45, alias="nextHop")


class VlanRule(RuleBase):
    """A switch port must be an access port in a given VLAN."""

    type: Literal["vlan"] = "vlan"
    device: str = Field(min_length=1, max_length=64)
    interface: str = Field(min_length=1, max_length=64)
    vlan: int = Field(ge=1, le=4094)


class DhcpPoolRule(RuleBase):
    type: Literal["dhcp_pool"] = "dhcp_pool"
    device: str = Field(min_length=1, max_length=64)
    network: str = Field(min_length=1, max_length=32)


class DeviceCountRule(RuleBase):
    """At least (and optionally at most) N devices of a kind must be present."""

    type: Literal["device_count"] = "device_count"
    kind: str = Field(min_length=1, max_length=32)
    minimum: int = Field(default=1, ge=0, le=64)
    maximum: int | None = Field(default=None, ge=0, le=64)


class LinkRule(RuleBase):
    """Two devices must be cabled together with a working link."""

    type: Literal["link"] = "link"
    source: str = Field(min_length=1, max_length=64)
    destination: str = Field(min_length=1, max_length=64)


GradingRule = Annotated[
    PingRule
    | NoPingRule
    | DnsRule
    | PortRule
    | DhcpLeaseRule
    | InterfaceAddressRule
    | InSubnetRule
    | GatewayRule
    | HostnameRule
    | StaticRouteRule
    | VlanRule
    | DhcpPoolRule
    | DeviceCountRule
    | LinkRule,
    Field(discriminator="type"),
]


# --------------------------------------------------------------------------- #
# Fault injection
# --------------------------------------------------------------------------- #
class FaultBase(AuthoringModel):
    id: str = Field(min_length=1, max_length=64)
    # Revealed only in the instructor view and in the post-mortem after a pass.
    explanation: str | None = Field(default=None, max_length=400)


class ShutdownInterfaceFault(FaultBase):
    type: Literal["shutdown_interface"] = "shutdown_interface"
    device: str = Field(min_length=1, max_length=64)
    interface: str = Field(min_length=1, max_length=64)


class WrongAddressFault(FaultBase):
    """Corrupt an interface's address, mask, or both."""

    type: Literal["wrong_address"] = "wrong_address"
    device: str = Field(min_length=1, max_length=64)
    interface: str = Field(min_length=1, max_length=64)
    address: str | None = None
    mask: str | None = None


class WrongGatewayFault(FaultBase):
    type: Literal["wrong_gateway"] = "wrong_gateway"
    device: str = Field(min_length=1, max_length=64)
    gateway: str = Field(min_length=1, max_length=45)


class DisableLinkFault(FaultBase):
    type: Literal["disable_link"] = "disable_link"
    source: str = Field(min_length=1, max_length=64)
    destination: str = Field(min_length=1, max_length=64)


class WrongCableFault(FaultBase):
    type: Literal["wrong_cable"] = "wrong_cable"
    source: str = Field(min_length=1, max_length=64)
    destination: str = Field(min_length=1, max_length=64)
    cable: str = Field(default="crossover", max_length=32)


class WrongVlanFault(FaultBase):
    type: Literal["wrong_vlan"] = "wrong_vlan"
    device: str = Field(min_length=1, max_length=64)
    interface: str = Field(min_length=1, max_length=64)
    vlan: int = Field(ge=1, le=4094)


class RemoveStaticRouteFault(FaultBase):
    type: Literal["remove_static_route"] = "remove_static_route"
    device: str = Field(min_length=1, max_length=64)
    network: str | None = Field(default=None, max_length=32)


FaultInjection = Annotated[
    ShutdownInterfaceFault
    | WrongAddressFault
    | WrongGatewayFault
    | DisableLinkFault
    | WrongCableFault
    | WrongVlanFault
    | RemoveStaticRouteFault,
    Field(discriminator="type"),
]


# --------------------------------------------------------------------------- #
# Learner-facing projections
# --------------------------------------------------------------------------- #
class LabSummary(APIModel):
    """A card in the lab library."""

    id: uuid.UUID
    slug: str
    title: str
    description: str | None
    kind: LabKind
    scenario_type: ScenarioType | None
    difficulty: Difficulty
    estimated_minutes: int
    passing_score: int
    xp_reward: int
    objective_count: int = 0
    # Populated for the signed-in learner, so the library shows what is done.
    best_score: float | None = None
    status: AttemptStatus | None = None


class LabDetail(LabSummary):
    """Everything a student may see before starting.

    Deliberately carries neither `grading_rules` nor `fault_injections`.
    """

    requirements: list[str]
    objectives: list[LabObjective]
    time_limit_seconds: int | None


class CheckResult(APIModel):
    """The outcome of one grading rule."""

    rule_id: str
    objective_id: str | None
    passed: bool
    points_earned: int
    points_possible: int
    # What the student should read: what was checked, and what was found.
    summary: str
    detail: str | None = None


class ObjectiveResult(APIModel):
    """Rolled up per objective, which is what the checklist renders."""

    objective_id: str
    title: str
    passed: bool
    points_earned: int
    points_possible: int


class LabAttemptRead(APIModel):
    """A learner's attempt, including their working copy of the topology."""

    id: uuid.UUID
    lab_id: uuid.UUID
    attempt_number: int
    status: AttemptStatus
    working_topology: dict[str, object]
    check_results: list[CheckResult]
    score_percent: float | None
    hints_used: int
    time_spent_seconds: int
    started_at: datetime | None
    submitted_at: datetime | None


class LabGradeResult(APIModel):
    """The response to "check my work" and to a final submission."""

    attempt_id: uuid.UUID
    lab_id: uuid.UUID
    status: AttemptStatus
    passed: bool
    score_percent: float
    points_earned: int
    points_possible: int
    passing_score: int
    results: list[CheckResult]
    objectives: list[ObjectiveResult]
    # Only set on a graded submission, and only the first time it passes.
    xp_awarded: int = 0
    total_xp: int = 0
    level: int = 1
    leveled_up: bool = False
    # Revealed once the lab is passed: what was broken to begin with.
    fault_explanations: list[str] = Field(default_factory=list)
    new_achievements: list[AchievementRead] = Field(default_factory=list)


class WorkingTopologyUpdate(APIModel):
    """Autosave of the canvas into the attempt."""

    document: TopologyDocument
    time_spent_seconds: int = Field(default=0, ge=0, le=86_400)


class HintRequest(APIModel):
    objective_id: str = Field(min_length=1, max_length=64)


class HintResponse(APIModel):
    objective_id: str
    hint: str | None
    hints_used: int


class LabWrite(APIModel):
    """Authoring payload — instructors and above only."""

    slug: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    kind: LabKind = LabKind.GUIDED
    scenario_type: ScenarioType | None = None
    difficulty: Difficulty = Difficulty.BEGINNER
    requirements: list[str] = Field(default_factory=list)
    objectives: list[LabObjective] = Field(default_factory=list)
    initial_topology: TopologyDocument
    grading_rules: list[GradingRule] = Field(default_factory=list)
    fault_injections: list[FaultInjection] = Field(default_factory=list)
    estimated_minutes: int = Field(default=30, ge=1, le=600)
    time_limit_seconds: int | None = Field(default=None, ge=60, le=86_400)
    passing_score: int = Field(default=80, ge=0, le=100)
    xp_reward: int = Field(default=50, ge=0, le=1000)
    is_published: bool = False
