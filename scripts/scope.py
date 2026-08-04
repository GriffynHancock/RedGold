"""scope.yaml — schema, parser, validator.

Build order step 2 (spec §5.1, §6).

This module is the *only* place that decides what a valid authorization boundary looks like.
`scope_guard.py` (step 3) reads its output and never reparses the file itself.

Design notes that are load-bearing, not decoration:

- **Parse errors are not exceptions the caller may ignore.** Every failure raises `ScopeError`.
  A caller that is enforcing a boundary must treat any `ScopeError` as DENY, never as "no scope
  restrictions found". Failing to load a boundary is not the same as having no boundary.

- **PyYAML is a hard dependency, and its absence is reported loudly.** On the reference machine
  `/usr/bin/python3` has PyYAML while the linuxbrew `python3` earlier on PATH does not. A hook
  invoked as bare `python3` would therefore die on import — and a hook that dies is a hook that
  does not deny. `require_yaml()` exists so that failure names itself instead of surfacing as a
  bare traceback.

- **`ceiling` may lower a mode's default, never raise it** (§6). This is enforced here rather than
  in the guard, so the boundary is already normalised by the time anything enforces it.
"""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ScopeError(Exception):
    """Any failure to load or validate a boundary. Callers must treat this as DENY."""


class ScopeDependencyError(ScopeError):
    """PyYAML is unavailable to the running interpreter."""


def require_yaml():
    """Import PyYAML, or fail with an error that says how to fix it.

    Kept separate from module import so that a missing dependency produces an actionable
    message rather than an ImportError traceback from inside a hook.
    """
    try:
        import yaml  # noqa: PLC0415
    except ModuleNotFoundError as exc:  # pragma: no cover - environment-dependent
        import sys

        raise ScopeDependencyError(
            "PyYAML is not available to this interpreter "
            f"({sys.executable}). RedGold cannot parse a scope boundary without it, and "
            "cannot safely proceed without a boundary. Install it for THIS interpreter "
            "(e.g. 'pip install pyyaml'), or point the hook at an interpreter that has it "
            "-- on Debian/Kali, /usr/bin/python3 usually does."
        ) from exc
    return yaml


# HackerOne's published scope vocabulary (§5.1), plus RedGold's four additions. Deliberately
# borrowed rather than invented so the document reads like one a client's lawyer has seen.
ASSET_TYPES = frozenset(
    {
        "URL",
        "WILDCARD",
        "CIDR",
        "IP_ADDRESS",
        "API",
        "SOURCE_CODE",
        "HARDWARE",
        "AI_MODEL",
        "SMART_CONTRACT",
        "APPLE_STORE_APP_ID",
        "GOOGLE_PLAY_APP_ID",
        "TESTFLIGHT",
        "DOWNLOADABLE_EXECUTABLES",
        "OTHER_APK",
        "OTHER_IPA",
        "OTHER",
        # RedGold extensions -- the asset classes this client base actually has.
        "CLOUD_ACCOUNT",
        "GITHUB_ORG",
        "SUPABASE_PROJECT",
        "FIREBASE_PROJECT",
    }
)

MODES = ("posture", "audit", "redteam")

# A mode sets the DEFAULT ceiling. scope.yaml may declare a lower one; never a higher one (§6).
MODE_DEFAULT_CEILING = {"posture": 1, "audit": 2, "redteam": 3}

ENGAGEMENT_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class AssetEntry:
    asset_type: str
    pattern: str
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"asset_type": self.asset_type, "pattern": self.pattern}
        if self.note is not None:
            d["note"] = self.note
        return d


@dataclass(frozen=True)
class Authorization:
    document: str
    signed_by: str
    signed_date: _dt.date
    window_start: _dt.date
    window_end: _dt.date
    emergency_contact: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "document": self.document,
            "signed_by": self.signed_by,
            "signed_date": self.signed_date,
            "window_start": self.window_start,
            "window_end": self.window_end,
        }
        if self.emergency_contact is not None:
            d["emergency_contact"] = self.emergency_contact
        return d


@dataclass(frozen=True)
class Constraints:
    no_destructive: bool = True
    testing_window: str | None = None
    max_requests_per_burst: int | None = None
    forbidden_actions: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"no_destructive": self.no_destructive}
        if self.testing_window is not None:
            d["testing_window"] = self.testing_window
        if self.max_requests_per_burst is not None:
            d["max_requests_per_burst"] = self.max_requests_per_burst
        if self.forbidden_actions:
            d["forbidden_actions"] = list(self.forbidden_actions)
        return d


@dataclass(frozen=True)
class Scope:
    engagement_id: str
    client_name: str
    client_contact: str
    authorization: Authorization
    mode: str
    ceiling: int
    in_scope: tuple[AssetEntry, ...]
    out_of_scope: tuple[AssetEntry, ...] = ()
    crown_jewels: tuple[str, ...] = ()
    constraints: Constraints = field(default_factory=Constraints)
    notify_before_active: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Serialise back to the scope.yaml document shape. Round-trip stable."""
        d: dict[str, Any] = {
            "engagement_id": self.engagement_id,
            "client": {"name": self.client_name, "contact": self.client_contact},
            "authorization": self.authorization.to_dict(),
            "mode": self.mode,
            "ceiling": self.ceiling,
        }
        if self.crown_jewels:
            d["crown_jewels"] = list(self.crown_jewels)
        d["in_scope"] = [e.to_dict() for e in self.in_scope]
        if self.out_of_scope:
            d["out_of_scope"] = [e.to_dict() for e in self.out_of_scope]
        d["constraints"] = self.constraints.to_dict()
        d["notify"] = {"before_active": self.notify_before_active}
        return d

    def dumps(self) -> str:
        yaml = require_yaml()
        return yaml.safe_dump(self.to_dict(), sort_keys=False, allow_unicode=True)


def _require(mapping: Any, key: str, where: str) -> Any:
    if not isinstance(mapping, dict):
        raise ScopeError(f"{where} must be a mapping, got {type(mapping).__name__}")
    if key not in mapping:
        raise ScopeError(f"{where} is missing required key '{key}'")
    return mapping[key]


def _require_str(mapping: Any, key: str, where: str) -> str:
    value = _require(mapping, key, where)
    if not isinstance(value, str) or not value.strip():
        raise ScopeError(f"{where}.{key} must be a non-empty string")
    return value


def _coerce_date(value: Any, where: str) -> _dt.date:
    # PyYAML already yields date objects for unquoted ISO dates; accept a string too so a
    # quoted date is not a spurious rejection.
    if isinstance(value, _dt.datetime):
        return value.date()
    if isinstance(value, _dt.date):
        return value
    if isinstance(value, str):
        try:
            return _dt.date.fromisoformat(value.strip())
        except ValueError as exc:
            raise ScopeError(f"{where} is not an ISO date (YYYY-MM-DD): {value!r}") from exc
    raise ScopeError(f"{where} must be an ISO date, got {type(value).__name__}")


def _parse_assets(raw: Any, where: str, *, required: bool) -> tuple[AssetEntry, ...]:
    if raw is None:
        if required:
            raise ScopeError(f"{where} is required and must list at least one asset")
        return ()
    if not isinstance(raw, list):
        raise ScopeError(f"{where} must be a list")
    if required and not raw:
        raise ScopeError(f"{where} must list at least one asset -- an empty boundary authorises nothing")

    entries: list[AssetEntry] = []
    for i, item in enumerate(raw):
        at = f"{where}[{i}]"
        asset_type = _require_str(item, "asset_type", at)
        if asset_type not in ASSET_TYPES:
            raise ScopeError(
                f"{at}.asset_type '{asset_type}' is not a recognised asset type. "
                f"Valid types: {', '.join(sorted(ASSET_TYPES))}"
            )
        pattern = _require_str(item, "pattern", at)
        note = item.get("note")
        if note is not None and not isinstance(note, str):
            raise ScopeError(f"{at}.note must be a string if present")
        entries.append(AssetEntry(asset_type=asset_type, pattern=pattern, note=note))
    return tuple(entries)


def _parse_constraints(raw: Any) -> Constraints:
    if raw is None:
        return Constraints()
    if not isinstance(raw, dict):
        raise ScopeError("constraints must be a mapping")

    no_destructive = raw.get("no_destructive", True)
    if not isinstance(no_destructive, bool):
        raise ScopeError("constraints.no_destructive must be a boolean")

    testing_window = raw.get("testing_window")
    if testing_window is not None and not isinstance(testing_window, str):
        raise ScopeError("constraints.testing_window must be a string if present")

    burst = raw.get("max_requests_per_burst")
    if burst is not None:
        # bool is a subclass of int; 'max_requests_per_burst: true' is a mistake, not a cap.
        if isinstance(burst, bool) or not isinstance(burst, int) or burst < 1:
            raise ScopeError("constraints.max_requests_per_burst must be a positive integer")

    forbidden = raw.get("forbidden_actions", [])
    if not isinstance(forbidden, list) or not all(isinstance(x, str) for x in forbidden):
        raise ScopeError("constraints.forbidden_actions must be a list of strings")

    return Constraints(
        no_destructive=no_destructive,
        testing_window=testing_window,
        max_requests_per_burst=burst,
        forbidden_actions=tuple(forbidden),
    )


def parse(document: Any) -> Scope:
    """Validate an already-deserialised scope document and return a Scope."""
    if not isinstance(document, dict):
        raise ScopeError("scope.yaml must be a mapping at the top level")

    engagement_id = _require_str(document, "engagement_id", "scope")
    if not ENGAGEMENT_ID_RE.match(engagement_id):
        raise ScopeError(
            f"engagement_id '{engagement_id}' must be lowercase alphanumeric words "
            "separated by single hyphens (e.g. 'acme-2026-08')"
        )

    client = _require(document, "client", "scope")
    client_name = _require_str(client, "name", "client")
    client_contact = _require_str(client, "contact", "client")

    auth_raw = _require(document, "authorization", "scope")
    signed_date = _coerce_date(_require(auth_raw, "signed_date", "authorization"), "authorization.signed_date")
    window_start = _coerce_date(_require(auth_raw, "window_start", "authorization"), "authorization.window_start")
    window_end = _coerce_date(_require(auth_raw, "window_end", "authorization"), "authorization.window_end")
    if window_end < window_start:
        raise ScopeError(
            f"authorization.window_end ({window_end}) precedes window_start ({window_start})"
        )
    emergency_contact = auth_raw.get("emergency_contact")
    if emergency_contact is not None and not isinstance(emergency_contact, str):
        raise ScopeError("authorization.emergency_contact must be a string if present")

    authorization = Authorization(
        document=_require_str(auth_raw, "document", "authorization"),
        signed_by=_require_str(auth_raw, "signed_by", "authorization"),
        signed_date=signed_date,
        window_start=window_start,
        window_end=window_end,
        emergency_contact=emergency_contact,
    )

    mode = _require_str(document, "mode", "scope")
    if mode not in MODES:
        raise ScopeError(f"mode '{mode}' must be one of: {', '.join(MODES)}")

    # §6: redteam requires a named emergency contact. Enforced here so the boundary cannot be
    # loaded at all without one, rather than discovered when something has already gone wrong.
    if mode == "redteam" and not (emergency_contact and emergency_contact.strip()):
        raise ScopeError(
            "mode 'redteam' requires authorization.emergency_contact -- a named person "
            "reachable at the time of execution (§6)"
        )

    ceiling = _require(document, "ceiling", "scope")
    if isinstance(ceiling, bool) or not isinstance(ceiling, int):
        raise ScopeError("ceiling must be an integer")
    if not 0 <= ceiling <= 3:
        raise ScopeError(f"ceiling {ceiling} is outside the tier range 0-3 (§6)")
    default_ceiling = MODE_DEFAULT_CEILING[mode]
    if ceiling > default_ceiling:
        raise ScopeError(
            f"ceiling {ceiling} exceeds the default ceiling for mode '{mode}' ({default_ceiling}). "
            "A declared ceiling may lower a mode's default but never raise it (§6)."
        )

    crown_jewels = document.get("crown_jewels", [])
    if not isinstance(crown_jewels, list) or not all(isinstance(x, str) for x in crown_jewels):
        raise ScopeError("crown_jewels must be a list of strings")

    in_scope = _parse_assets(document.get("in_scope"), "in_scope", required=True)
    out_of_scope = _parse_assets(document.get("out_of_scope"), "out_of_scope", required=False)

    notify = document.get("notify") or {}
    if not isinstance(notify, dict):
        raise ScopeError("notify must be a mapping")
    notify_before_active = notify.get("before_active", True)
    if not isinstance(notify_before_active, bool):
        raise ScopeError("notify.before_active must be a boolean")

    return Scope(
        engagement_id=engagement_id,
        client_name=client_name,
        client_contact=client_contact,
        authorization=authorization,
        mode=mode,
        ceiling=ceiling,
        in_scope=in_scope,
        out_of_scope=out_of_scope,
        crown_jewels=tuple(crown_jewels),
        constraints=_parse_constraints(document.get("constraints")),
        notify_before_active=notify_before_active,
    )


def loads(text: str) -> Scope:
    yaml = require_yaml()
    try:
        document = yaml.safe_load(text)
    except Exception as exc:  # yaml.YAMLError and anything else the loader raises
        raise ScopeError(f"scope.yaml is not valid YAML: {exc}") from exc
    return parse(document)


def load(path: str | Path) -> Scope:
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as exc:
        raise ScopeError(f"cannot read scope file {p}: {exc}") from exc
    return loads(text)
