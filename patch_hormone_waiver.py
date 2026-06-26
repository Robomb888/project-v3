"""
patch_hormone_waiver.py
-----------------------
Add  "waived_if": ["hormones_not_desired_or_contraindicated"]  to the
hormone_duration_months requirement, per insurer, with breast augmentation
controlled separately:

  WAIVER_INSURERS             -> waive for NON-breast-augmentation surgeries
  BREAST_AUG_WAIVER_INSURERS  -> ALSO waive for breast augmentation
                                 (only where breast augmentation does NOT depend
                                 on estrogen-induced breast growth before surgery)

The two lists are independent: an insurer can waive generally, only for breast
augmentation, both, or neither.

After patching, a coverage check simulates how a breast-augmentation letter
resolves (breast_aug -> top -> all_surgeries, per your run_checker cascade) and
flags any mismatch between what you asked for and what the rules actually do --
in EITHER direction (waived when it shouldn't be, or not waived when it should
be) -- since shared/inherited rule files can carry the waiver across surgeries.

Idempotent. Only adds waived_if to existing hormone_duration_months
requirements; it never creates or deletes a requirement.

Usage:
    python patch_hormone_waiver.py --insurers uhc cigna --breast-aug-insurers cigna
    python patch_hormone_waiver.py --rules path/to/rules --breast-aug-insurers medica
    python patch_hormone_waiver.py            # lists insurers if none chosen
"""
import argparse
import json
from pathlib import Path

WAIVER = "hormones_not_desired_or_contraindicated"

# Insurers that waive hormone duration for NON-breast-augmentation surgeries.
WAIVER_INSURERS = {
    "aetna", "healthpartners", "medica", "medicare", "mhcp_medicaid", "uhc", "wpath_soc8_reference"
}

# Insurers that ALSO waive it for breast augmentation. Use only where breast
# augmentation does NOT require estrogen-induced breast growth before surgery.
BREAST_AUG_WAIVER_INSURERS = {
    "aetna", "healthpartners","medicare", "mhcp_medicaid", "wpath_soc8_reference"
}

BREAST_AUG_PREFIX = "breast_aug"
BREAST_AUG_STEMS = ["breast_aug", "top", "all_surgeries"]   # mirrors run_checker cascade
AGE_GROUPS = ["adult", "minor"]


def _insurer_of(rules_dir, jf):
    rel = jf.relative_to(rules_dir).parts
    return rel[0] if len(rel) > 1 else None


def _add_waiver(jf):
    """Add the waiver to hormone_duration_months in this file. Returns True if changed."""
    data = json.loads(jf.read_text(encoding="utf-8"))
    reqs = data.get("requirements")
    if not isinstance(reqs, list):
        return False
    touched = False
    for r in reqs:
        if r.get("field") == "hormone_duration_months":
            w = r.setdefault("waived_if", [])
            if WAIVER not in w:
                w.append(WAIVER)
                touched = True
    if touched:
        jf.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return touched


def patch(rules_dir, general, breast):
    patched, skipped = [], []
    for jf in sorted(rules_dir.rglob("*.json")):
        insurer = _insurer_of(rules_dir, jf)
        if insurer not in (general | breast):
            continue
        is_ba = jf.stem.startswith(BREAST_AUG_PREFIX)
        allowed = (insurer in breast) if is_ba else (insurer in general)
        if not allowed:
            if is_ba:
                skipped.append(jf)
            continue
        if _add_waiver(jf):
            patched.append(jf)
    return patched, skipped


def breast_aug_coverage(rules_dir, general, breast):
    """Compare the desired breast-aug waiver state to the resolved one."""
    try:
        from rules_engine import load_rules
    except Exception:
        return []
    issues = []
    for insurer in sorted(general | breast):
        idir = rules_dir / insurer
        if not idir.is_dir():
            continue
        desired = insurer in breast
        for ag in AGE_GROUPS:
            target = next((idir / f"{stem}_{ag}.json"
                           for stem in BREAST_AUG_STEMS
                           if (idir / f"{stem}_{ag}.json").exists()), None)
            if target is None:
                continue
            try:
                resolved = load_rules(target)
            except Exception as e:
                issues.append((insurer, ag, target, "error", f"could not resolve ({e})"))
                continue
            waived = any(r.get("field") == "hormone_duration_months" and r.get("waived_if")
                         for r in resolved["requirements"])
            has_hormone = any(r.get("field") == "hormone_duration_months"
                              for r in resolved["requirements"])
            if not has_hormone:
                continue
            if waived and not desired:
                issues.append((insurer, ag, target, "waived_but_should_not", ""))
            elif desired and not waived:
                issues.append((insurer, ag, target, "should_but_not_waived", ""))
    return issues


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rules", default="rules", help="rules directory (default: ./rules)")
    ap.add_argument("--insurers", nargs="*", help="insurers to waive for non-breast-aug surgeries")
    ap.add_argument("--breast-aug-insurers", nargs="*", help="insurers to ALSO waive for breast augmentation")
    args = ap.parse_args()

    rules_dir = Path(args.rules)
    general = set(args.insurers) if args.insurers is not None else set(WAIVER_INSURERS)
    breast = set(args.breast_aug_insurers) if args.breast_aug_insurers is not None else set(BREAST_AUG_WAIVER_INSURERS)

    available = sorted(p.name for p in rules_dir.iterdir() if p.is_dir()) if rules_dir.is_dir() else []
    if not (general | breast):
        print("No insurers selected. Edit the allowlists or pass --insurers / --breast-aug-insurers.")
        print("Available insurers:", ", ".join(available) or "(none found)")
        return

    unknown = (general | breast) - set(available)
    if unknown:
        print("Warning: not found under", rules_dir, "->", ", ".join(sorted(unknown)))

    patched, skipped = patch(rules_dir, general, breast)
    print(f"patched {len(patched)} file(s):")
    for p in patched:
        print("   +", p)
    if skipped:
        print(f"left {len(skipped)} breast-augmentation file(s) non-waivable:")
        for s in skipped:
            print("   -", s)

    issues = breast_aug_coverage(rules_dir, general, breast)
    if not issues:
        print("\ncoverage check: breast augmentation matches your settings for every selected insurer. OK")
        return
    print("\n!! coverage check found mismatches:")
    for insurer, ag, target, kind, extra in issues:
        if kind == "waived_but_should_not":
            print(f"   {insurer}/{ag}: breast-aug resolves to {target.name} which IS waived, but this "
                  f"insurer is not in the breast-aug list.")
            print("      Fix: add a non-waived hormone_duration_months override to a breast_aug rule, "
                  "or move the hormone requirement out of the shared file.")
        elif kind == "should_but_not_waived":
            print(f"   {insurer}/{ag}: breast-aug should be waived but resolves to {target.name} which is NOT "
                  f"waived (it inherits a non-waived requirement).")
            print("      Fix: add a waived hormone_duration_months override to the breast_aug rule, "
                  "or include this insurer in --insurers so the shared file is waived.")
        else:
            print(f"   {insurer}/{ag}: {extra} ({target.name})")


if __name__ == "__main__":
    main()