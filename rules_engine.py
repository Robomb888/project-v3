import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

_TRUE_STRINGS = {"true", "yes", "y", "1"}
_FALSE_STRINGS = {"false", "no", "n", "0"}
_EMPTYISH = {
    "", "none", "n/a", "na", "null", "nil", "unknown",
    "not stated", "not specified", "not provided", "not mentioned",
}

def load_rules(path):
    """Load a rule file, resolving any `extends` chain.

    A rule file may contain:
      "extends": "_base.json"            (or a list, applied left-to-right)
      "remove":  ["field_a", "field_b"] (drop inherited requirements)
      "requirements": [...]             (added last; same field overrides parent)
    Requirements are keyed by `field`; later layers win. Paths in `extends`
    are relative to the file that declares them.
    """
    path = Path(path).resolve()
    resolved = _resolve(path, seen={path})
    _validate_rule_file(resolved, str(path))
    return resolved


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _resolve(path, seen):
    raw = _read(path)
    extends = raw.get("extends", [])
    if isinstance(extends, str):
        extends = [extends]

    merged = {}# field -> rule (dict preserves insertion order)
    metadata = {}

    for rel in extends:
        parent_path = (path.parent / rel).resolve()
        if parent_path in seen:
            raise ValueError(f"Circular 'extends': {parent_path} (from {path})")
        if not parent_path.exists():
            raise FileNotFoundError(f"{path} extends '{rel}', but {parent_path} does not exist.")
        parent = _resolve(parent_path, seen | {parent_path})
        metadata.update({k: v for k, v in parent.items() if k != "requirements"})
        for rule in parent["requirements"]:
            merged[rule["field"]] = rule

    # this file's metadata (insurance/surgery/age_group/...) wins over parents
    metadata.update({k: v for k, v in raw.items()
                     if k not in ("requirements", "extends", "remove")})

    for field in raw.get("remove", []):
        merged.pop(field, None)

    for rule in raw.get("requirements", []):
        merged[rule["field"]] = rule          # add or override by field

    return {**metadata, "requirements": list(merged.values())}


def _validate_rule_file(rules, path):
    if not isinstance(rules, dict) or not isinstance(rules.get("requirements"), list):
        raise ValueError(f"Rule file {path}: must resolve to an object with a 'requirements' list.")
    for i, rule in enumerate(rules["requirements"]):
        for key in ("field", "type"):
            if key not in rule:
                raise ValueError(f"Rule file {path}: requirement #{i} is missing '{key}'.")
        if rule["type"] in ("min", "boolean") and "value" not in rule:
            raise ValueError(
                f"Rule file {path}: requirement '{rule['field']}' (type {rule['type']}) needs a 'value'."
            )
        if rule["type"] == "min" and (isinstance(rule.get("value"), bool)
                                      or not isinstance(rule.get("value"), (int, float))):
            raise ValueError(
                f"Rule file {path}: requirement '{rule['field']}' (min) needs a numeric 'value', "
                f"got {rule.get('value')!r}."
            )
        if "waived_if" in rule and not (isinstance(rule["waived_if"], list)
                                        and all(isinstance(w, str) for w in rule["waived_if"])):
            raise ValueError(
                f"Rule file {path}: requirement '{rule['field']}' has a 'waived_if' "
                f"that must be a list of field names."
            )


def _to_number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _to_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        s = value.strip().lower()
        if s in _TRUE_STRINGS:
            return True
        if s in _FALSE_STRINGS:
            return False
    return None


def _is_present(value):
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in _EMPTYISH
    return True


def evaluate_rules(extracted, rules):
    results = []
    for rule in rules["requirements"]:
        field = rule["field"]
        rtype = rule["type"]
        value = extracted.get(field)

        # A rule may declare "waived_if": [field, ...]; if any named signal is
        # present/true in the extraction, the requirement is waived (met).
        waived = [w for w in rule.get("waived_if", []) if _is_present(extracted.get(w))]
        if waived:
            status, reason = "met", f"Requirement waived ({', '.join(waived)})."
        elif value is None:
            status, reason = "missing", "Field not found."
        elif rtype == "min":
            num = _to_number(value)
            threshold = rule["value"]
            if num is None:
                status, reason = "error", f"Could not read {value!r} as a number."
            elif num >= threshold:
                status, reason = "met", f"{num:g} >= {threshold:g}."
            else:
                status, reason = "not_met", f"{num:g} < {threshold:g}."
        elif rtype == "boolean":
            parsed = _to_bool(value)
            expected = rule["value"]
            if parsed is None:
                status, reason = "error", f"Could not read {value!r} as true/false."
            elif parsed == expected:
                status, reason = "met", f"Value is {parsed}, as required."
            else:
                status, reason = "not_met", f"Value is {parsed}, expected {expected}."
        elif rtype == "exists":
            if _is_present(value):
                status, reason = "met", f"Present: {value!r}."
            else:
                status, reason = "not_met", f"No meaningful value ({value!r})."
        else:
            status, reason = "error", f"Unknown rule type {rtype!r}."

        result = {
            "field": field,
            "actual": value,
            "status": status,
            "passed": status == "met",
            "reason": reason,
        }
        if "label" in rule:
            result["label"] = rule["label"]
        results.append(result)

    return results