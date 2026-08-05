# Parts 5 & 6 — Device Configuration Engine and Cisco CLI

Built together, at your request, because the two must edit **the same model**.
An `ip address` typed at the CLI and the same values entered in a form have to
be indistinguishable afterwards — if they were separate systems that would be a
synchronisation problem, and it would eventually drift.

## The design that makes it work

One `DeviceConfig` model (`app/schemas/device_config.py`) fills
`TopologyDevice.config`, the field Part 4 deliberately left untyped. Three
things read and write it:

```
  configuration forms  ─┐
                        ├─►  DeviceConfig  ──►  show running-config
  Cisco CLI engine     ─┘                       show ip interface brief
                                                show ip route
```

`show running-config` is not a display convenience — it is the proof the two
editors agree. Verified end to end in the browser in both directions: an
address typed at the CLI appeared in the interface form, and an address changed
in the form appeared in `show running-config` and `show ip interface brief`.

## Part 5 — Device Configuration Engine

Double-clicking a device opens a configuration window whose tabs depend on what
the device actually is. A switch gets VLANs; a router gets routing; a PC gets
neither, because showing a VLAN database on a PC teaches the wrong model.

Configurable: hostname, enable secret, banner, per-interface addressing (static
or DHCP), description, speed, duplex, administrative state, switchport mode,
access/voice/native VLANs and trunk allow-lists, default gateway, DNS servers,
VLAN database, static routes, OSPF, EIGRP, RIP, DHCP pools, standard and
extended ACLs, NAT (static, dynamic, overload), and wireless settings.

**Validation is real.** Addresses must parse; masks must be **contiguous**
(255.255.0.255 parses as an address but is not a legal mask, and IOS rejects
it); VLAN ids must be in range; an address requires a mask; two interfaces
cannot sit in the same subnet.

**Warnings are advisory, not blocking.** A half-finished configuration is a
normal state while learning. The window surfaces the classic mistakes as you
work:

* a default gateway that is in none of the connected networks
* an interface that is cabled but has no address
* an interface configured but administratively down — *"it needs 'no shutdown'"*
* two interfaces in one subnet

## Part 6 — Cisco CLI

A console on every router, switch, multilayer switch and firewall. Eight IOS
modes with correct prompts and transitions (`R1>`, `R1#`, `R1(config)#`,
`R1(config-if)#`, `R1(config-vlan)#`, `R1(config-router)#`, `(dhcp-config)#`,
`(config-line)#`), `exit` stepping up one level and `end` jumping straight out.

**Abbreviations work**, because nobody types commands in full: `conf t`,
`int g0/0`, `sh ip int br`, `no shut`. Interface names are matched against both
the full and short forms in the device catalogue, and the number may be a
separate token (`int gi 0/1`), because textbooks vary.

**Errors are worded as IOS words them** — `% Invalid input detected at '^'
marker.` with the caret under the offending token, `% Incomplete command.`,
`% Ambiguous command`. Reading real device output is a skill; a simulator that
says "unknown command" does not teach it.

Commands implemented: `enable`, `disable`, `configure terminal`, `hostname`,
`interface`, `ip address` (including `dhcp`), `shutdown`/`no shutdown`,
`description`, `speed`, `duplex`, `switchport` (mode, access/voice vlan, trunk
native and allowed), `vlan`/`name`, `ip route`, `ip default-gateway`,
`ip name-server`, `ip dhcp pool` with `network`/`default-router`/`dns-server`,
`router ospf|eigrp|rip` with `network`, `router-id`, `passive-interface`,
`auto-summary`, `version`, `access-list` (standard and extended, with named
ports like `eq www`), `ip access-group`, `ip nat inside|outside` and
`ip nat inside source` (static/dynamic/overload), `enable secret`, `banner
motd`, `line`, `copy running-config startup-config`, `write`, and `show`
(`running-config`, `startup-config`, `ip interface brief`, `ip route`,
`vlan brief`, `version`, `access-lists`, `ip nat`).

The terminal itself has command history (↑/↓), tab completion scoped to the
current mode, and Ctrl-Z. It is a plain scrolling div with a hidden input, not a
terminal emulator library — there is no cursor addressing or colour escapes
here, so a 200 kB emulator would buy nothing.

**Sessions are stateless on the server.** The terminal holds the mode and
selected interface and sends them with each line, so there is no per-connection
state to expire, leak, or need sticky routing.

## Verified

| Check | Result |
|---|---|
| Backend tests | 270 passed (200 → 270) |
| Frontend tests | 78 passed |
| `ruff check` | clean |
| `mypy app` | clean, 72 files |
| `tsc -b` | clean |
| `eslint` | clean |
| `vite build` | succeeds |
| `alembic check` | no drift |

The 56 CLI tests are a behavioural contract: if a learner follows a CCNA
textbook transcript, it works. They cover mode transitions, every abbreviation
form, address and mask rejection, overlapping-subnet refusal, VLANs, trunking,
all three routing protocols, DHCP, ACLs, NAT, and every `show` command.

Driven end to end in the browser: opened a router's window, saw the live
"cabled but has no IP address" warning, ran a full configuration session at the
CLI, watched the prompt change through each mode, confirmed `show ip interface
brief` rendered, then switched to the Interfaces tab and found the CLI's address
in the form — and changed it there and found it back in `show running-config`.

## Decisions worth flagging

**Interfaces start administratively down.** Real routers do, and forgetting
`no shutdown` is the single most common reason a correctly addressed link does
not work. Starting them up would remove the lesson.

**A non-contiguous mask is rejected.** 255.255.0.255 is a real misconception,
not a typo, and saying so is more useful than accepting it.

**`ping` is honest about not working yet.** It prints the IOS preamble and then
says the packet simulation engine is Part 7. Faking a successful ping when
nothing was forwarded would teach exactly the wrong thing.

**Unknown-but-harmless commands are accepted.** `service password-encryption`,
`spanning-tree ...` and line settings parse and are ignored, because rejecting
them would break a learner following a textbook transcript for reasons that
have nothing to do with what they are learning.

**Configuration is not auto-persisted.** The endpoints validate and render but
save nothing; the editor writes the returned configuration into its document and
persists on the topology's own Save. That keeps the unsaved-changes model from
Part 4 intact.

## What this unlocks

The simulator is now genuinely configurable: you can build a topology, cable it,
give every device addresses and routing, and inspect it exactly as you would a
real device.

What it still cannot do is **move a packet**. `ping` says so plainly. Part 7 —
the packet simulation engine (ARP, DHCP, DNS, ICMP, TCP/UDP with animated flow)
— is what turns this configuration into observable behaviour, and it is where
the miscabled links from Part 4 and the configuration warnings from Part 5 stop
being advisory and start actually failing.
