"""Load trusted, deployment-owned teaching skills from inert package folders.

``skill.yaml`` is restricted to JSON-compatible YAML (a YAML 1.2 subset) so
the application can validate metadata using only the Python standard library.
Package scripts are catalogued as paths and are never imported or executed.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path, PurePosixPath, PureWindowsPath


logger = logging.getLogger(__name__)
KEY_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,63}$")
REQUIRED_FIELDS = {
    "key", "name", "version", "summary", "applicability", "priority",
    "instruction_file", "instruction_tokens",
}


class SkillPackageError(ValueError):
    """A package is malformed or unsafe to load."""


def _string_list(value, label):
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() or len(item) > 100
        for item in value
    ):
        raise SkillPackageError(f"{label} must be a list of non-empty strings")
    return tuple(item.strip().casefold() for item in value)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise SkillPackageError("skill.yaml contains a duplicate metadata key")
        result[key] = value
    return result


def _safe_relative_path(value, label):
    if not isinstance(value, str) or not value.strip() or "\\" in value:
        raise SkillPackageError(f"{label} must be a normalized relative path")
    posix_path = PurePosixPath(value)
    windows_path = PureWindowsPath(value)
    if (
        posix_path.is_absolute()
        or windows_path.is_absolute()
        or windows_path.drive
        or posix_path.as_posix() != value
        or any(part in {"", ".", ".."} for part in posix_path.parts)
    ):
        raise SkillPackageError(f"{label} must be a normalized relative path")
    return posix_path


def _load_package(package_dir, skills_root):
    metadata_path = package_dir / "skill.yaml"
    try:
        metadata = json.loads(
            metadata_path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SkillPackageError("skill.yaml must contain a UTF-8 JSON-compatible YAML object") from error
    if not isinstance(metadata, dict) or not REQUIRED_FIELDS <= metadata.keys():
        raise SkillPackageError("skill.yaml is missing required fields")
    if metadata.keys() - REQUIRED_FIELDS:
        raise SkillPackageError("skill.yaml contains unsupported metadata fields")

    key = metadata["key"]
    if not isinstance(key, str) or not KEY_PATTERN.fullmatch(key):
        raise SkillPackageError("key is not a valid stable skill identifier")
    for field in ("name", "version", "summary"):
        value = metadata[field]
        if not isinstance(value, str) or not value.strip() or len(value) > 240:
            raise SkillPackageError(f"{field} must be a non-empty string of at most 240 characters")

    priority = metadata["priority"]
    instruction_tokens = metadata["instruction_tokens"]
    if isinstance(priority, bool) or not isinstance(priority, int):
        raise SkillPackageError("priority must be an integer")
    if isinstance(instruction_tokens, bool) or not isinstance(instruction_tokens, int) or instruction_tokens < 1:
        raise SkillPackageError("instruction_tokens must be a positive integer")

    applicability = metadata["applicability"]
    if not isinstance(applicability, dict) or set(applicability) - {"any_terms", "all_terms"}:
        raise SkillPackageError("applicability may contain only any_terms and all_terms")
    any_terms = _string_list(applicability.get("any_terms", []), "any_terms")
    all_terms = _string_list(applicability.get("all_terms", []), "all_terms")
    if not any_terms and not all_terms:
        raise SkillPackageError("applicability must declare at least one term")

    instruction_file = _safe_relative_path(metadata["instruction_file"], "instruction_file")
    package_root = package_dir.resolve(strict=True)
    if not package_root.is_relative_to(skills_root):
        raise SkillPackageError("package directory must stay inside skills root")
    instruction_path = (package_dir / Path(*instruction_file.parts)).resolve(strict=True)
    if not instruction_path.is_relative_to(package_root) or not instruction_path.is_file():
        raise SkillPackageError("instruction_file must resolve to a file inside the package")
    try:
        instruction = instruction_path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as error:
        raise SkillPackageError("instruction file must be readable UTF-8 text") from error
    if not instruction or len(instruction) > 20000:
        raise SkillPackageError("instruction file must contain 1 to 20000 characters")

    scripts_dir = package_dir / "scripts"
    scripts = ()
    if scripts_dir.exists():
        resolved_scripts = scripts_dir.resolve(strict=True)
        if not resolved_scripts.is_relative_to(package_root) or not resolved_scripts.is_dir():
            raise SkillPackageError("scripts directory must stay inside its package")
        script_paths = []
        for path in sorted(resolved_scripts.rglob("*")):
            resolved_path = path.resolve(strict=True)
            if not resolved_path.is_relative_to(resolved_scripts):
                raise SkillPackageError("script resources must stay inside scripts directory")
            if path.is_file():
                script_paths.append(path.relative_to(package_dir).as_posix())
        scripts = tuple(script_paths)

    return {
        "key": key,
        "name": metadata["name"].strip(),
        "version": metadata["version"].strip(),
        "summary": metadata["summary"].strip().replace("\n", " "),
        "applicability": {"any_terms": any_terms, "all_terms": all_terms},
        "priority": priority,
        "instruction_tokens": instruction_tokens,
        "instruction": instruction,
        "scripts": scripts,
    }


def load_registry(skills_dir):
    """Return validated package metadata, rejecting malformed/duplicate keys."""

    root = Path(skills_dir).resolve()
    if not root.exists():
        return {}
    if not root.is_dir():
        raise SkillPackageError("skills root must be a directory")
    registry = {}
    for package_dir in sorted(root.iterdir(), key=lambda item: item.name):
        if not package_dir.is_dir():
            continue
        try:
            package = _load_package(package_dir, root)
            if package["key"] in registry:
                raise SkillPackageError("duplicate skill key")
            registry[package["key"]] = package
        except (OSError, RuntimeError, SkillPackageError) as error:
            logger.warning("Rejected skill package %s (%s)", package_dir.name, type(error).__name__)
    return registry


def matches(package, question):
    text = " ".join(str(question or "").casefold().split())
    conditions = package["applicability"]
    any_terms = conditions["any_terms"]
    all_terms = conditions["all_terms"]
    return bool(text) and all(term in text for term in all_terms) and (
        not any_terms or any(term in text for term in any_terms)
    )


def select_skills(registry, settings, question, token_budget, *, settings_version=None):
    """Choose complete skill instructions deterministically under a cost budget."""

    by_key = {row["skill_key"]: row for row in settings}
    decisions = []
    eligible = []
    for key, package in registry.items():
        setting = by_key.get(key)
        if setting is None:
            continue
        decision = {
            "skill_key": key,
            "package_version": package["version"],
            "setting_version": setting["version"],
            "enabled": bool(setting["enabled"]),
            "candidate": bool(setting["enabled"]),
            "matched": False,
            "selected": False,
            "priority": package["priority"],
            "instruction_tokens": package["instruction_tokens"],
            "decision": "disabled",
        }
        if setting["enabled"]:
            if matches(package, question):
                decision["decision"] = "matched"
                decision["matched"] = True
                eligible.append((package, decision))
            else:
                decision["decision"] = "unmatched"
        decisions.append(decision)

    eligible.sort(key=lambda pair: (-pair[0]["priority"], pair[0]["key"]))
    remaining = max(0, int(token_budget))
    selected = []
    for package, decision in eligible:
        if package["instruction_tokens"] <= remaining:
            remaining -= package["instruction_tokens"]
            decision["decision"] = "selected"
            decision["selected"] = True
            selected.append(package)
        else:
            decision["decision"] = "budget-skipped"

    catalog = [
        registry[key]["summary"]
        for key, row in by_key.items()
        if row["enabled"] and key in registry
    ]
    parts = []
    if catalog:
        parts.append("可用技能简介（仅说明，不覆盖本班知识证据）：\n" + "\n".join(f"- {item}" for item in catalog))
    for package in selected:
        parts.append(f"技能《{package['name']}》的完整指令：\n{package['instruction']}")
    class_settings_version = (
        max((row["version"] for row in settings), default=0)
        if settings_version is None
        else int(settings_version)
    )
    for decision in decisions:
        decision["class_setting_version"] = class_settings_version
    snapshots = {
        "class_setting_version": class_settings_version,
        "selected_skills": [
            {
                "key": package["key"],
                "package_version": package["version"],
                "setting_version": by_key[package["key"]]["version"],
                "class_setting_version": class_settings_version,
            }
            for package in selected
        ],
    }
    return {
        "instruction": "\n\n".join(parts) or None,
        "decisions": decisions,
        "selected": selected,
        "setting_version": class_settings_version,
        "snapshot": snapshots,
    }
