from __future__ import annotations

import json
import hashlib
import os
import tempfile
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from app_paths import CONFIG_PATH, PRESETS_PATH, LABELS_PATH, PROFILE_DATA_DIR, DEFAULT_CONFIG

from .settings_schema import PROFILE_KEYS as GAME_PROFILE_KEYS
from .storage_policy import StorageError, current_policy
from .labels import LabelDefinition, LabelState, state_from_records, unique_names

FAVORITES_KEY = "__favorites__"
LABEL_DEFINITIONS_KEY = "__label_definitions__"
DEFAULT_FAVORITE_SCOPE = "__default__"

def load_json(path: Path, default):
    try:
        with path.open("r", encoding="utf-8") as f:
            value = json.load(f)
        if current_policy().strict and not isinstance(value, type(default)):
            raise StorageError(f"Invalid data in {path}: expected {type(default).__name__}. Repair the file before continuing.")
        return value
    except FileNotFoundError:
        return deepcopy(default)
    except (OSError, ValueError, UnicodeError) as error:
        if current_policy().strict:
            raise StorageError(f"Cannot read {path}: {error}. Repair the file or its permissions before continuing.") from error
        return default

def save_json(path: Path, data) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, prefix=path.name + ".", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

def load_config() -> Dict:
    cfg = load_json(CONFIG_PATH, deepcopy(DEFAULT_CONFIG))
    if current_policy().strict:
        _validate_config(cfg)
    for key, val in DEFAULT_CONFIG.items():
        cfg.setdefault(key, val)
    cfg = normalize_game_profiles(cfg)
    return cfg


def _validate_config(cfg: Dict) -> None:
    from . import settings_schema

    profiles = cfg.get("game_profiles", [])
    if not isinstance(profiles, list) or any(not isinstance(profile, dict) for profile in profiles):
        raise StorageError("game_profiles must be a list of game profile objects. Repair config.json.")
    for profile in profiles:
        identifier = profile.get("id", "")
        if not isinstance(identifier, str) or any(character in identifier for character in "/\\:\0") or identifier in {".", ".."}:
            raise StorageError("Invalid game profile ID in config.json; IDs must be plain file name components.")
    for values in (cfg, *profiles):
        for spec in (*settings_schema.all_specs(), *settings_schema.GAME_PROFILE_FIELDS):
            if spec.key not in values:
                continue
            value = values[spec.key]
            if spec.kind == settings_schema.INT:
                if isinstance(value, bool):
                    raise StorageError(f"{spec.label} must be a whole number. Repair config.json.")
                settings_schema.parse_int(spec, value)
            elif spec.kind == settings_schema.FLAG:
                if not isinstance(value, bool) and not (spec.key in GAME_PROFILE_KEYS and value == ""):
                    raise StorageError(f"{spec.label} must be true or false. Repair config.json.")
            elif not isinstance(value, str):
                raise StorageError(f"{spec.label} must be text. Repair config.json.")
            elif spec.kind == settings_schema.CHOICE and value and value not in spec.choices:
                raise StorageError(f"{spec.label} must be one of: {', '.join(spec.choices)}. Repair config.json.")

def save_config(cfg: Dict) -> None:
    save_json(CONFIG_PATH, normalize_game_profiles(dict(cfg)))

def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")

def profile_id_for(name: str, created_at: str) -> str:
    raw = f"{name.strip()}|{created_at.strip()}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def _unique_profile_id(name: str, created_at: str, used: set[str]) -> str:
    identifier = profile_id_for(name, created_at)
    sequence = 0
    while identifier in used:
        sequence += 1
        identifier = profile_id_for(name, f"{created_at}|{sequence}")
    return identifier

def game_abbreviation(name: str) -> str:
    words = [part for part in "".join(ch if ch.isalnum() else " " for ch in name).split() if part]
    if len(words) >= 2:
        return (words[0][0] + words[1][0]).upper()
    if words:
        return words[0][:2].upper()
    return "??"

def _profile_from_legacy(cfg: Dict) -> Dict | None:
    if not any(cfg.get(key) not in (None, "", False, DEFAULT_CONFIG.get(key)) for key in GAME_PROFILE_KEYS):
        return None
    name = str(cfg.get("game_name") or "Default game").strip() or "Default game"
    created_at = str(cfg.get("game_profile_created_at") or _now_iso())
    profile = {
        "id": profile_id_for(name, created_at),
        "name": name,
        "created_at": created_at,
    }
    for key in GAME_PROFILE_KEYS:
        profile[key] = cfg.get(key, "")
    return profile

def normalize_game_profiles(cfg: Dict) -> Dict:
    profiles = [p for p in cfg.get("game_profiles", []) if isinstance(p, dict)]
    normalized = []
    seen = set()
    for profile in profiles:
        name = str(profile.get("name") or "Game").strip() or "Game"
        created_at = str(profile.get("created_at") or _now_iso())
        profile_id = str(profile.get("id") or profile_id_for(name, created_at))
        if profile_id in seen:
            profile_id = _unique_profile_id(name, created_at, seen)
        seen.add(profile_id)
        item = {"id": profile_id, "name": name, "created_at": created_at}
        for key in GAME_PROFILE_KEYS:
            value = profile.get(key, DEFAULT_CONFIG.get(key, ""))
            item[key] = DEFAULT_CONFIG[key] if value == "" and isinstance(DEFAULT_CONFIG[key], bool) else value
        normalized.append(item)

    if not normalized:
        legacy = _profile_from_legacy(cfg)
        if legacy:
            normalized.append(legacy)

    active_id = str(cfg.get("active_game_profile_id") or "")
    if normalized and not any(p["id"] == active_id for p in normalized):
        active_id = normalized[0]["id"]
    if not normalized:
        active_id = ""

    cfg["game_profiles"] = normalized
    cfg["active_game_profile_id"] = active_id
    active = active_game_profile(cfg)
    if active:
        for key in GAME_PROFILE_KEYS:
            cfg[key] = active.get(key, "")
    return cfg

def active_game_profile(cfg: Dict | None = None) -> Dict | None:
    if cfg is None:
        cfg = load_json(CONFIG_PATH, DEFAULT_CONFIG.copy())
    active_id = str(cfg.get("active_game_profile_id") or "")
    for profile in cfg.get("game_profiles", []) or []:
        if isinstance(profile, dict) and profile.get("id") == active_id:
            return profile
    profiles = cfg.get("game_profiles", []) or []
    return profiles[0] if profiles else None

def create_game_profile(name: str, values: Dict | None = None, cfg: Dict | None = None) -> Dict:
    values = values or {}
    created_at = str(values.get("created_at") or _now_iso())
    used = {profile["id"] for profile in (cfg or {}).get("game_profiles", [])}
    profile = {
        "id": _unique_profile_id(name, created_at, used),
        "name": str(name or "Game").strip() or "Game",
        "created_at": created_at,
    }
    for key in GAME_PROFILE_KEYS:
        profile[key] = values.get(key, DEFAULT_CONFIG.get(key, ""))
    if cfg is not None:
        cfg.setdefault("game_profiles", []).append(profile)
        cfg["active_game_profile_id"] = profile["id"]
        normalize_game_profiles(cfg)
    return profile

def update_game_profile(cfg: Dict, profile_id: str, values: Dict) -> bool:
    for profile in cfg.get("game_profiles", []):
        if profile.get("id") == profile_id:
            if "name" in values:
                profile["name"] = str(values.get("name") or "Game").strip() or "Game"
            for key in GAME_PROFILE_KEYS:
                if key in values:
                    profile[key] = values[key]
            normalize_game_profiles(cfg)
            return True
    return False

def set_active_game_profile(cfg: Dict, profile_id: str) -> bool:
    if any(profile.get("id") == profile_id for profile in cfg.get("game_profiles", [])):
        cfg["active_game_profile_id"] = profile_id
        normalize_game_profiles(cfg)
        return True
    return False

def delete_game_profile(cfg: Dict, profile_id: str) -> bool:
    profiles = cfg.get("game_profiles", [])
    kept = [profile for profile in profiles if profile.get("id") != profile_id]
    if len(kept) == len(profiles):
        return False
    cfg["game_profiles"] = kept
    if not kept:
        for key in GAME_PROFILE_KEYS:
            cfg[key] = DEFAULT_CONFIG[key]
    if cfg.get("active_game_profile_id") == profile_id:
        cfg["active_game_profile_id"] = kept[0]["id"] if kept else ""
    normalize_game_profiles(cfg)
    return True

def _active_profile_context(base_path: Path) -> tuple[Path, Dict | None, Dict]:
    raw = load_config()
    profile = active_game_profile(raw)
    if not profile:
        return base_path, None, raw
    if current_policy().migrate:
        PROFILE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return PROFILE_DATA_DIR / f"{profile['id']}-{base_path.name}", profile, raw

def _active_profile_data_path(base_path: Path) -> Path:
    path, _profile, _cfg = _active_profile_context(base_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path

def _is_first_profile(profile: Dict | None, cfg: Dict) -> bool:
    profiles = cfg.get("game_profiles", []) or []
    return bool(profile and profiles and profiles[0].get("id") == profile.get("id"))

def _merge_legacy_records(profile_data, legacy_data):
    if not isinstance(profile_data, dict) or not isinstance(legacy_data, dict):
        return profile_data
    if LABEL_DEFINITIONS_KEY in profile_data:
        return profile_data
    merged = dict(profile_data)
    changed = False
    for name, legacy_value in legacy_data.items():
        if name in (FAVORITES_KEY, LABEL_DEFINITIONS_KEY):
            continue
        current = merged.get(name)
        if current is None:
            merged[name] = legacy_value
            changed = True
        elif isinstance(current, dict) and isinstance(legacy_value, dict):
            legacy_label = legacy_value.get("label")
            if legacy_label and not current.get("label"):
                current = dict(current)
                current["label"] = legacy_label
                current.setdefault("last_managed", legacy_value.get("last_managed"))
                current.setdefault("state", legacy_value.get("state", "undefined"))
                merged[name] = current
                changed = True
        elif isinstance(current, dict) and legacy_value and not current.get("label"):
            current = dict(current)
            current["label"] = legacy_value
            merged[name] = current
            changed = True
    return merged if changed else profile_data

def _mod_record_data(base_path: Path, data):
    if base_path != LABELS_PATH or not isinstance(data, dict):
        return data
    return {name: value for name, value in data.items() if name != FAVORITES_KEY}

def _load_profile_json(base_path: Path, default):
    path, profile, cfg = _active_profile_context(base_path)
    if path == base_path:
        return load_json(path, default)
    is_legacy_profile = base_path.exists() and _is_first_profile(profile, cfg)
    if not path.exists():
        if is_legacy_profile:
            data = _mod_record_data(base_path, load_json(base_path, default))
            if current_policy().migrate:
                save_json(path, data)
            return data
        return load_json(path, default)
    data = load_json(path, default)
    if is_legacy_profile:
        merged = _merge_legacy_records(data, _mod_record_data(base_path, load_json(base_path, default)))
        if merged is not data:
            if current_policy().migrate:
                save_json(path, merged)
            return merged
    return data

def load_presets() -> Dict[str, List[str]]:
    records = load_preset_records()
    return {name: rec.get("mods", []) for name, rec in records.items()}

def save_presets(presets: Dict[str, List[str]]) -> None:
    current = load_preset_records()
    data = {}
    for name, mods in presets.items():
        rec = current.get(name, {})
        data[name] = {
            "mods": mods,
            "last_managed": rec.get("last_managed"),
            "state": rec.get("state", "undefined"),
        }
    save_json(_active_profile_data_path(PRESETS_PATH), data)
    _sync_legacy_records(PRESETS_PATH, data)


def _sync_legacy_records(base_path: Path, records: Dict) -> None:
    path, profile, cfg = _active_profile_context(base_path)
    if path == base_path or not _is_first_profile(profile, cfg) or not base_path.exists():
        return
    legacy = load_json(base_path, {})
    updated = dict(legacy)
    for name in legacy:
        if base_path == LABELS_PATH and name == FAVORITES_KEY:
            continue
        if name not in records:
            updated.pop(name)
        else:
            updated[name] = records[name]
    if updated != legacy:
        save_json(base_path, updated)

def load_labels() -> Dict[str, str]:
    records = load_mod_records()
    return {name: rec.get("label", "") for name, rec in records.items() if rec.get("label")}

def save_labels(labels: Dict[str, str]) -> None:
    current = load_mod_records()
    data = {}
    for name, label in labels.items():
        rec = current.get(name, {})
        data[name] = {
            "label": label,
            "labels": [label] if label else [],
            "last_managed": rec.get("last_managed"),
            "state": rec.get("state", "undefined"),
        }
    for name, rec in current.items():
        if name not in data and (rec.get("last_managed") or rec.get("state") != "undefined"):
            data[name] = {
                "label": "",
                "labels": [],
                "last_managed": rec.get("last_managed"),
                "state": rec.get("state", "undefined"),
            }
    _save_mod_record_data(data)

def _now() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")

def load_mod_records() -> Dict[str, Dict]:
    raw = _mod_record_data(LABELS_PATH, _load_profile_json(LABELS_PATH, {}))
    data = {}
    changed = False
    for name, value in raw.items():
        if name == LABEL_DEFINITIONS_KEY:
            continue
        if current_policy().strict:
            label = value.get("label", "") if isinstance(value, dict) else value
            if not isinstance(label, str):
                raise StorageError("Invalid mod label metadata: labels must be text.")
            if isinstance(value, dict) and "labels" in value and (
                not isinstance(value["labels"], list) or any(not isinstance(item, str) for item in value["labels"])
            ):
                raise StorageError("Invalid mod label metadata: labels must be a list of names.")
        if isinstance(value, dict):
            data[name] = {
                **value,
                "label": value.get("label", ""),
                "last_managed": value.get("last_managed"),
                "state": value.get("state", "undefined"),
            }
        else:
            data[name] = {
                "label": value or "",
                "last_managed": None,
                "state": "undefined",
            }
            changed = True
    if changed and current_policy().migrate:
        _save_mod_record_data(data)
    return data

def save_mod_records(records: Dict[str, Dict]) -> None:
    _save_mod_record_data(records)

def _save_mod_record_data(records: Dict[str, Dict]) -> None:
    path = _active_profile_data_path(LABELS_PATH)
    data = dict(records)
    current = load_json(path, {})
    if LABEL_DEFINITIONS_KEY not in data and LABEL_DEFINITIONS_KEY in current:
        data[LABEL_DEFINITIONS_KEY] = current[LABEL_DEFINITIONS_KEY]
    if path == LABELS_PATH:
        current = load_json(LABELS_PATH, {})
        favorites = current.get(FAVORITES_KEY) if isinstance(current, dict) else None
        if isinstance(favorites, dict) and favorites:
            data[FAVORITES_KEY] = favorites
    save_json(path, data)
    _sync_legacy_records(LABELS_PATH, data)


def load_label_definitions() -> dict[str, LabelDefinition]:
    raw = _load_profile_json(LABELS_PATH, {}).get(LABEL_DEFINITIONS_KEY, {})
    if not isinstance(raw, dict):
        raise StorageError("Invalid label definitions: expected an object.")
    result = {}
    for name, value in raw.items():
        if not isinstance(value, dict) or value.get("mode", "manual") not in ("manual", "automatic"):
            raise StorageError(f"Invalid definition for label: {name}")
        terms = value.get("terms", [])
        if not isinstance(terms, list) or any(not isinstance(term, str) for term in terms):
            raise StorageError(f"Invalid name fragments for label: {name}")
        result[name] = LabelDefinition(value.get("mode", "manual"), unique_names(terms))
    return result


def load_label_state() -> LabelState:
    return state_from_records(load_mod_records(), load_label_definitions())


def save_label_state(state: LabelState) -> None:
    state.validate()
    records = load_mod_records()
    for name in records.keys() | state.assignments.keys():
        record = records.setdefault(name, {"last_managed": None, "state": "undefined"})
        names = state.assignments.get(name, [])
        record["labels"] = list(names)
        record["label"] = names[0] if names else ""
    records[LABEL_DEFINITIONS_KEY] = {
        name: {"mode": definition.mode, "terms": list(definition.terms)}
        for name, definition in state.definitions.items()
    }
    _save_mod_record_data(records)

def _favorite_scope(cfg: Dict) -> str:
    return str(cfg.get("active_game_profile_id") or DEFAULT_FAVORITE_SCOPE)

def load_favorites(cfg: Dict) -> set[str]:
    data = load_json(LABELS_PATH, {})
    favorites = data.get(FAVORITES_KEY, {}) if isinstance(data, dict) else {}
    values = favorites.get(_favorite_scope(cfg), []) if isinstance(favorites, dict) else []
    return {str(name) for name in values if str(name)}

def update_favorites(cfg: Dict, names: List[str], favorite: bool) -> set[str]:
    data = load_json(LABELS_PATH, {})
    if not isinstance(data, dict):
        data = {}
    favorite_map = data.get(FAVORITES_KEY, {})
    if not isinstance(favorite_map, dict):
        favorite_map = {}
    else:
        favorite_map = dict(favorite_map)
    scope = _favorite_scope(cfg)
    selected = {str(name) for name in favorite_map.get(scope, []) if str(name)}
    targets = {str(name) for name in names if str(name)}
    selected = selected | targets if favorite else selected - targets
    if selected:
        favorite_map[scope] = sorted(selected, key=str.lower)
    else:
        favorite_map.pop(scope, None)
    if favorite_map:
        data[FAVORITES_KEY] = favorite_map
    else:
        data.pop(FAVORITES_KEY, None)
    save_json(LABELS_PATH, data)
    return selected

def mark_mods_managed(names: List[str], state: str) -> None:
    records = load_mod_records()
    managed_at = _now()
    for name in names:
        rec = records.setdefault(name, {"label": "", "last_managed": None, "state": "undefined"})
        rec["last_managed"] = managed_at
        rec["state"] = state
    save_mod_records(records)

def ensure_mod_records(names: List[str]) -> None:
    if not current_policy().migrate:
        return
    records = load_mod_records()
    changed = False
    for name in names:
        if name not in records:
            records[name] = {"label": "", "last_managed": None, "state": "undefined"}
            changed = True
    if changed:
        save_mod_records(records)

def load_preset_records() -> Dict[str, Dict]:
    raw = _load_profile_json(PRESETS_PATH, {})
    data = {}
    changed = False
    for name, value in raw.items():
        if current_policy().strict:
            members = value.get("mods", []) if isinstance(value, dict) else value
            if not isinstance(members, list) or any(not isinstance(member, str) for member in members):
                raise StorageError("Invalid preset metadata: mods must be a list of names.")
        if isinstance(value, dict):
            data[name] = {
                "mods": value.get("mods", []),
                "last_managed": value.get("last_managed"),
                "state": value.get("state", "undefined"),
            }
        else:
            data[name] = {
                "mods": value or [],
                "last_managed": None,
                "state": "undefined",
            }
            changed = True
    if changed and current_policy().migrate:
        save_json(_active_profile_data_path(PRESETS_PATH), data)
    return data

def save_preset_records(records: Dict[str, Dict]) -> None:
    save_json(_active_profile_data_path(PRESETS_PATH), records)

def mark_preset_managed(name: str, state: str) -> None:
    records = load_preset_records()
    rec = records.setdefault(name, {"mods": [], "last_managed": None, "state": "undefined"})
    rec["last_managed"] = _now()
    rec["state"] = state
    save_preset_records(records)
