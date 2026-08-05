# Part 4 — Interactive Network Designer

Scope as specified: drag-and-drop topology builder, device placement, cable
system, zoom and pan, save/load projects.

## Delivered

### Device catalogue
Sixteen device kinds with **real Cisco interface names** — `GigabitEthernet0/0`,
`FastEthernet0/24`, `Serial0/0/0` — and realistic port counts modelled on actual
hardware: a Catalyst 2960 has 24 FastEthernet access ports plus two Gigabit
uplinks and a console; an ISR 2911 has three Gigabit interfaces and two serial
slots.

This is not cosmetic. Part 5 configures these interfaces, Part 6's CLI addresses
them by name, and Part 7 forwards frames across them. A learner who types
`interface g0/0` later must be talking about the port they cabled here, so the
catalogue is served from the backend and shared by all of them rather than
duplicated per feature.

### Cable system
Six cable types, with the correct one **inferred from real MDI/MDI-X rules**:
devices with the same pinout (PC↔PC, switch↔switch, router↔router) need a
crossover; opposite pinouts (PC↔switch, router↔switch) need a straight-through.
Port type wins over device type, so two serial interfaces get a serial cable and
any wireless interface gets a wireless link.

Choosing the wrong cable is a **warning, not an error**. The point of a teaching
simulator is to let a learner make the classic mistake, see it flagged with an
explanation of *why* it is wrong, and fix it. Part 7 will refuse to pass traffic
over a miscabled link — which is exactly what happens in a real wiring closet.

Cable type is encoded in the line itself: solid straight-through, dashed
crossover, dotted wireless, thick amber serial, blue fibre. The cabling is
readable without clicking anything.

### Connection model
Devices expose **one connection handle, not one per interface**. A 2960 has 26
usable ports; rendering 26 targets would make the node unusable and force a
learner to pick a port number before they know what one is. Joining two devices
asks the server for the lowest free compatible port on each end and the right
cable; both stay editable in the inspector afterwards.

### Structural validation
The topology document is fully validated on save. Part 1 chose JSON storage on
the grounds that the editor always reads and writes whole topologies; this is
what makes that safe:

* link endpoints must name devices that exist
* interfaces must exist on that device's kind
* **an interface carries at most one cable** — you cannot plug two cables into
  one port
* ids are unique, group references resolve, unknown keys are rejected

That third rule is what stops a topology that looks fine on screen from being
physically impossible to build.

### Editor
Drag from the palette or click to drop; drag devices freely; zoom, pan, minimap
and fit-to-view; rename and label devices; group them into labelled areas;
undo/redo; import and export; Ctrl/Cmd+S to save.

Two design decisions inside the editor are worth stating:

**The document is the single source of truth.** React Flow nodes and edges are
*derived* from it on every render rather than held in parallel. Keeping two
copies and syncing them is how these editors accumulate bugs — a drag updates
one, a save reads the other, and they disagree.

**Undo/redo snapshots whole documents.** Documents are a few kilobytes even at
the 200-device ceiling, so a bounded stack of snapshots is far simpler than
inverse operations and cannot drift from real state. A drag is one undo step,
not one per animation frame.

### Persistence
Save, load, list, duplicate, delete, and a portable export format. Exports
describe a *network*, not a database row — no ids, ownership or timestamps — so
a topology can be shared and re-imported anywhere. `device_count` is derived
from the document on every write rather than trusted from the client, so the
summary can never disagree with what it summarises.

Ownership is enforced **in the query**, not checked afterwards, so no code path
loads another user's topology into memory first. A topology you cannot read
returns 404, not 403, so the endpoint cannot enumerate ids.

## Verified

| Check | Result |
|---|---|
| Backend tests | 200 passed (160 → 200) |
| Frontend tests | 78 passed (64 → 78) |
| `ruff check` | clean |
| `mypy app` | clean, 65 files |
| `tsc -b` | clean |
| `eslint` | clean |
| `vite build` | succeeds |
| `alembic check` | no drift |

Driven end to end against running servers: built a six-device small-office
network (2 PCs, a server, a switch, a router, an ISP) with five cables including
one deliberate miscable; the server flagged it with an explanation; the canvas
drew warning badges on exactly the two affected devices and rendered live port
counts (SW1 4/26, R1 2/5); fixed the cable through the inspector, saved, and
confirmed the change persisted with zero outstanding warnings.

## Bug found and fixed during verification

**`MissingGreenlet` on every write path that returns a timestamp.** `updated_at`
carries `onupdate=func.now()`, so after an UPDATE SQLAlchemy marks it expired
and reloads it on first access — which under asyncio raises rather than quietly
querying. It surfaced on topology update and duplicate.

The same class of bug appeared in Part 3 with a relationship, and I fixed that
one locally. This time I fixed the class: `eager_defaults` on the declarative
base makes every server-generated value come back via RETURNING in the original
statement. That covers every model, including ones not yet written.

## Decisions worth flagging

**Cable correctness teaches rather than blocks.** Modern gear auto-negotiates
MDI/MDI-X, so a purist could argue crossover rules are obsolete — but CCNA
examines them, labs depend on them, and a learner who has never seen the mistake
will not recognise it in a wiring closet.

**One handle per device.** The alternative — a handle per interface — is more
"faithful" and much worse to use. Faithfulness is preserved where it matters:
the link records real interfaces, and they are editable.

**Save is explicit, not autosaved.** A learner experimenting with a design may
well want to abandon it. Autosaving would overwrite work they intended to keep.
An unsaved-changes indicator and Ctrl/Cmd+S cover the ergonomics.

**Panning is not an edit.** Moving the viewport neither marks the document dirty
nor enters undo history; it is persisted with the next real save.

## Not in this part

Device configuration — addresses, VLANs, routing, ACLs — is Part 5. The
`TopologyDevice.config` field exists and round-trips untouched, deliberately
untyped here so this schema needs no knowledge of what an ACL looks like.

**Animated packet flow across links is Part 7**, not this part. The brief lists
it under the simulator, but it is the visible output of the packet simulation
engine; drawing animations with no simulation behind them would be a decoration
that later has to be thrown away. Links already carry an `enabled` flag for
Part 8's fault injection.

Konva is not installed. React Flow covers node-graph editing with pan, zoom and
connection handling; Konva is a general 2D canvas library, and the natural place
for it is Part 7's packet animation layer, where per-frame drawing over the
topology actually needs it.

## Ready for Part 5

Part 5 (device configuration engine) fills in `TopologyDevice.config` — a
double-click opens a configuration window for hostname, addressing, DHCP,
routing and the rest. The device catalogue already tells it which interfaces
each device has, and the topology tells it what they are connected to.
