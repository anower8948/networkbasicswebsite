"""Tokenising, abbreviation matching, and IOS error messages.

Two behaviours separate a CLI that feels real from one that does not:

* **Abbreviations.** Nobody types `configure terminal` or
  `show ip interface brief` in full. IOS accepts any unambiguous prefix, so
  `conf t` and `sh ip int br` must work, and an ambiguous prefix must say so.
* **Error messages.** `% Invalid input detected at '^' marker.` with the caret
  under the offending token is how IOS tells you where you went wrong. Getting
  that right teaches learners to read real device output.
"""

from __future__ import annotations

import re

from app.models.enums import DeviceKind
from app.services.device_catalog import spec_for


def tokenize(line: str) -> list[str]:
    """Split a command line, collapsing runs of whitespace."""
    return line.strip().split()


def matches(token: str, full: str) -> bool:
    """True when `token` is a prefix of `full`.

    Case-insensitive, like IOS. A bare empty token never matches, so a stray
    space cannot select a command.
    """
    if not token:
        return False
    return full.lower().startswith(token.lower())


def resolve(token: str, candidates: list[str]) -> tuple[str | None, bool]:
    """Resolve an abbreviation against a candidate list.

    Returns `(match, ambiguous)`. An exact match always wins even when it is
    also a prefix of a longer command — `ip` should not be ambiguous just
    because `ipv6` exists.
    """
    lowered = token.lower()
    for candidate in candidates:
        if candidate.lower() == lowered:
            return candidate, False

    hits = [candidate for candidate in candidates if matches(token, candidate)]
    if len(hits) == 1:
        return hits[0], False
    if len(hits) > 1:
        return None, True
    return None, False


# --------------------------------------------------------------------------- #
# Errors, worded as IOS words them
# --------------------------------------------------------------------------- #
def invalid_input(line: str, token_index: int = 0) -> str:
    """`% Invalid input detected at '^' marker.`, with the caret positioned.

    IOS points at the *first character of the offending token*, which is what
    makes the message useful — the learner sees exactly which word it rejected.
    """
    tokens = tokenize(line)
    offset = 0
    if tokens and token_index < len(tokens):
        # Find where that token starts in the original text, so the caret lands
        # correctly even with irregular spacing.
        position = 0
        for index, token in enumerate(tokens):
            position = line.lower().find(token.lower(), position)
            if index == token_index:
                offset = position
                break
            position += len(token)

    return f"{' ' * offset}^\n% Invalid input detected at '^' marker.\n"


def incomplete_command() -> str:
    return "% Incomplete command.\n"


def ambiguous_command(token: str) -> str:
    return f'% Ambiguous command: "{token}"\n'


def unknown_command(line: str) -> str:
    return invalid_input(line, 0)


# --------------------------------------------------------------------------- #
# Interface names
# --------------------------------------------------------------------------- #
_INTERFACE_SPLIT = re.compile(r"^([a-zA-Z\-]+)\s*(.*)$")


def expand_interface(tokens: list[str], kind: DeviceKind) -> str | None:
    """Turn `g0/0`, `gi 0/0` or `GigabitEthernet0/0` into the canonical name.

    IOS accepts a bewildering range of abbreviations for interface names, and a
    learner following a textbook will type whichever the book used. This matches
    against both the full and short names the device catalogue defines, and
    tolerates the number being a separate token (`int g 0/0`).
    """
    if not tokens:
        return None

    # `int g 0/0` — join a bare-letters token with the following number.
    text = tokens[0]
    if len(tokens) > 1 and not any(char.isdigit() for char in text):
        text = f"{text}{tokens[1]}"

    match = _INTERFACE_SPLIT.match(text)
    if not match:
        return None
    prefix, number = match.group(1), match.group(2)

    interfaces = spec_for(kind).interfaces()
    for entry in interfaces:
        full = str(entry["name"])
        short = str(entry["shortName"])

        # Split each catalogue name the same way, then compare prefix + number.
        for candidate in (full, short):
            candidate_match = _INTERFACE_SPLIT.match(candidate)
            if not candidate_match:
                continue
            candidate_prefix, candidate_number = candidate_match.groups()
            if candidate_number != number:
                continue
            if matches(prefix, candidate_prefix):
                return full

    return None


def parse_vlan_list(text: str) -> list[int]:
    """Parse `10,20,30-32` as IOS accepts for allowed VLAN lists."""
    result: set[int] = set()
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_text, _, end_text = part.partition("-")
            try:
                start, end = int(start_text), int(end_text)
            except ValueError as exc:
                raise ValueError(f"Invalid VLAN range: {part}") from exc
            if start > end:
                raise ValueError(f"Invalid VLAN range: {part}")
            result.update(range(start, end + 1))
        else:
            try:
                result.add(int(part))
            except ValueError as exc:
                raise ValueError(f"Invalid VLAN id: {part}") from exc

    for vlan in result:
        if not 1 <= vlan <= 4094:
            raise ValueError(f"VLAN id {vlan} is out of range (1-4094).")
    return sorted(result)
