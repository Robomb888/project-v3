"""
run_checker.py
--------------
Checks a letter against insurance rules, falling back to an LLM only for fields
deterministic extraction missed -- and only for fields we actually have an
extractor for. Everything else unknown is flagged for human review.

Examples:
    python run_checker.py letter.pdf --insurance 1
    python run_checker.py            # fully interactive
"""
import argparse
import json
import logging
import time
from pathlib import Path

from pipeline import extract_all
from rules_engine import load_rules, evaluate_rules
from llm_fallback import run_llm_fallback
from ingestion.document import extract_from_document
from registry import FIELD_REGISTRY, FIELD_EXCEPTIONS      # <-- now also import FIELD_REGISTRY
import extractors as ex

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)

BASE = Path(__file__).resolve().parent
SAMPLES_DIR = BASE / "samples"
RULES_DIR = BASE / "rules"
RESULTS_DIR = BASE / "results"
DOC_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif"}


INSURANCE = {
    1: "uhc", 2: "aetna", 3: "bcbs_mn", 4: "cigna", 5: "healthpartners",
    6: "medica", 7: "medicare", 8: "mhcp_medicaid", 9: "primewest", 10: "ucare",
    11: "wpath_soc8_reference",
}
SURGERY = {1: "bottom", 2: "mastectomy", 3: "breast_aug", 4: "facial"}

# mastectomy/breast_aug cascade up to a "top" file; bottom stays bottom;
# facial has no category, so it falls through to all_surgeries
SURGERY_CATEGORY = {"mastectomy": "top", "breast_aug": "top", "bottom": "bottom", "orchiectomy": "bottom"}

ADULT_AGE = 18


def prompt_choice(prompt: str, options: dict[int, str]) -> str:
    menu = "\n".join(f"  {k}. {v}" for k, v in options.items())
    while True:
        raw = input(f"{prompt}\n{menu}\n> ").strip()
        if raw.isdigit() and int(raw) in options:
            return options[int(raw)]
        print("Invalid choice, please try again.")


def prompt_int(prompt: str) -> int:
    while True:
        raw = input(prompt).strip()
        if raw.isdigit():
            return int(raw)
        print("Please enter a number.")


def _normalize(s: str) -> str:
    return s.strip().lower().replace(" ", "_")


# rule file resolution
def resolve_rule_path(letter_text: str, insurance: str):
    """Detect (or prompt for) age + surgery, then cascade specific -> category
    -> all_surgeries within the age group. Returns a Path, or None if this
    insurer has no matching file (-> route to human review)."""
    detected_age = ex.age(letter_text)
    if detected_age is None:
        detected_age = prompt_int("Age could not be detected. Enter patient age: ")
    age_group = "adult" if detected_age >= ADULT_AGE else "minor"

    surgery = ex.surgery_type(letter_text)
    surgery = _normalize(surgery) if surgery else _normalize(
        prompt_choice("Surgery type not detected. Select one:", SURGERY)
    )

    stems = [surgery]
    category = SURGERY_CATEGORY.get(surgery)
    if category and category != surgery:
        stems.append(category)
    stems.append("all_surgeries")

    for stem in stems:
        candidate = RULES_DIR / insurance / f"{stem}_{age_group}.json"
        if candidate.exists():
            return candidate
    return None


# core processing
def run_system(letter_text: str, rules) -> dict:
    extracted = extract_all(letter_text)
    results = evaluate_rules(extracted, rules)

    log.info("extracted: %s", extracted)
    log.info("rule fields: %s", sorted(r["field"] for r in rules["requirements"]))
    rules_by_field = {r["field"]: r for r in rules["requirements"]}

    # Only ask the LLM about fields we actually have an extractor for. The new
    # checklist fields have no extractor, and the FIELD_EXCEPTIONS abstain on
    # purpose -- both go to human review, NOT the 4b model.
    missing = [rules_by_field[r["field"]] for r in results
               if r["actual"] is None
               and r["field"] in FIELD_REGISTRY
               and r["field"] not in FIELD_EXCEPTIONS]

    log.info("sent to LLM: %s", [m["field"] for m in missing])
    if missing:
        llm_result = run_llm_fallback(letter_text, missing)
        log.info("LLM returned: %s", llm_result)

        if isinstance(llm_result, str):
            try:
                llm_result = json.loads(llm_result)
            except json.JSONDecodeError:
                log.warning("LLM fallback returned unparseable output; ignoring it.")
                llm_result = {}
        # don't let a null answer clobber anything
        extracted.update({k: v for k, v in llm_result.items() if v is not None})
        results = evaluate_rules(extracted, rules)   # re-evaluate after fallback

    # Anything still unknown after extraction + LLM -> human review.
    # Never silently leave it as a plain "missing"/fail.
    for r in results:
        if r["status"] == "missing":
            r["status"] = "needs_review"
            r["passed"] = False

    return {"extracted": extracted, "evaluation": results}


def validate(evaluation: list[dict]) -> dict:
    failed = [r for r in evaluation if r["status"] == "not_met"]
    errors = [r for r in evaluation if r["status"] == "error"]
    review = [r for r in evaluation if r["status"] == "needs_review"]
    return {
        "passed": not failed and not errors and not review,   # auto-clear only if all met
        "failed": [f"{r['field']}: {r['reason']}" for r in failed],
        "errors": [f"{r['field']}: {r['reason']}" for r in errors],
        "needs_review": [r["field"] for r in review],
    }


def process_letter(file_path: Path, insurance: str) -> dict:
    letter = extract_from_document(str(file_path))

    rule_path = resolve_rule_path(letter, insurance)
    if rule_path is None:
        log.info("  no rule file for %s / this surgery+age -> manual review", insurance)
        return {
            "file": file_path.name,
            "insurance": insurance,
            "status": "needs_review",
            "reason": "No rule file for this insurer / surgery / age group.",
        }

    rules = load_rules(rule_path)
    meta = json.loads(rule_path.read_text(encoding="utf-8"))

    t0 = time.perf_counter()
    output = run_system(letter, rules)
    elapsed = time.perf_counter() - t0

    return {
        "file": file_path.name,
        #"mrn" 
        "insurance": meta.get("insurance"),
        "surgery": meta.get("surgery"),
        "age_group": meta.get("age_group"),
        "rule_file": str(rule_path.relative_to(BASE)),
        "validation": validate(output["evaluation"]),
        "evaluation": output["evaluation"],
        "execution_seconds": round(elapsed, 6),
    }


def render_report_pdf(report: dict, out_path: Path) -> None:
    """Write the review report as a PDF. The validation section is bold."""
    from xml.sax.saxutils import escape
    from reportlab.lib.pagesizes import letter as PAGE
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    styles = getSampleStyleSheet()
    normal = styles["Normal"]
    bold = ParagraphStyle("b", parent=normal, fontName="Helvetica-Bold")
    bold_big = ParagraphStyle("bb", parent=normal, fontName="Helvetica-Bold",
                              fontSize=13, spaceBefore=8, spaceAfter=4)
    cell = ParagraphStyle("cell", parent=normal, fontSize=8, leading=10)

    doc = SimpleDocTemplate(str(out_path), pagesize=PAGE,
                            topMargin=0.8 * inch, bottomMargin=0.8 * inch,
                            leftMargin=0.9 * inch, rightMargin=0.9 * inch,
                            title="Pre-Authorization Letter Review")
    story = [Paragraph("Letter of Support Review", styles["Title"]), Spacer(1, 6)]

    for k in ("file", "insurance", "surgery", "age_group", "rule_file"):
        if report.get(k) is not None:
            story.append(Paragraph(f"<b>{k.replace('_', ' ').capitalize()}:</b> "
                                   f"{escape(str(report[k]))}", normal))
    if report.get("execution_seconds") is not None:
        story.append(Paragraph(f"<b>Run time:</b> {report['execution_seconds']:.3f} s", normal))
    story.append(Spacer(1, 10))

    # ---- VALIDATION (bold) ----
    val = report.get("validation")
    if val is None:
        story.append(Paragraph(f"VALIDATION: {(report.get('status') or 'review').upper()}", bold_big))
        if report.get("reason"):
            story.append(Paragraph(f"<b>{escape(report['reason'])}</b>", bold))
    else:
        if val.get("failed") or val.get("errors"):
            outcome, color = "FAIL", "#b00020"
        elif val.get("needs_review"):
            outcome, color = "REVIEW", "#9a6700"
        else:
            outcome, color = "PASS", "#1a7f37"
        story.append(Paragraph(f'VALIDATION: <font color="{color}">{outcome}</font>', bold_big))

        def section(title, items):
            story.append(Paragraph(f"<b>{title} ({len(items)})</b>", bold))
            for it in (items or ["none"]):
                story.append(Paragraph(f"<b>\u2022 {escape(str(it))}</b>", bold))
            story.append(Spacer(1, 4))

        section("Failed", val.get("failed", []))
        section("Errors", val.get("errors", []))
        section("Needs review", val.get("needs_review", []))

    # ---- per-field detail (normal weight) ----
    ev = report.get("evaluation")
    if ev:
        story.append(Spacer(1, 8))
        story.append(Paragraph("Detail", styles["Heading2"]))
        status_color = {"met": "#1a7f37", "not_met": "#b00020", "error": "#b00020",
                        "needs_review": "#9a6700", "missing": "#666666"}
        rows = [[Paragraph("<b>Field</b>", cell), Paragraph("<b>Status</b>", cell),
                 Paragraph("<b>Reason</b>", cell)]]
        for r in ev:
            st = str(r.get("status", ""))
            rows.append([
                Paragraph(escape(str(r.get("field", ""))), cell),
                Paragraph(f'<font color="{status_color.get(st, "#000000")}"><b>{st}</b></font>', cell),
                Paragraph(escape(str(r.get("reason", ""))), cell),
            ])
        table = Table(rows, colWidths=[2.2 * inch, 1.0 * inch, 3.3 * inch], repeatRows=1)
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f7f7")]),
            ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(table)

    doc.build(story)


def write_report(file_stem: str, report: dict) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    # machine-readable JSON (used by the eval harness / audit trail)
    (RESULTS_DIR / f"{file_stem}_results.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")
    # human-readable PDF report (validation section in bold)
    pdf_path = RESULTS_DIR / f"{file_stem}_results.pdf"
    try:
        render_report_pdf(report, pdf_path)
        return pdf_path
    except Exception as e:
        log.warning("Could not write PDF (%s); wrote JSON only. Try: pip install reportlab", e)
        return RESULTS_DIR / f"{file_stem}_results.json"


# CLI
def gather_targets(raw_path: str | None) -> list[Path]:
    raw = raw_path or input("Enter the file or folder name: ").strip()
    target = Path(raw)
    if not target.is_absolute():
        target = SAMPLES_DIR / target
    if target.is_file():
        return [target]
    if target.is_dir():
        return sorted(p for p in target.iterdir() if p.suffix.lower() in DOC_SUFFIXES)
    raise FileNotFoundError(f"Not found: {target}")


def main():
    parser = argparse.ArgumentParser(description="Check letters against insurance rules.")
    parser.add_argument("path", nargs="?", help="File or folder (relative to samples/ or absolute).")
    parser.add_argument("--insurance", type=int, help="Insurance id (see menu).")
    args = parser.parse_args()

    insurance = (INSURANCE.get(args.insurance)
                 or prompt_choice("Select the insurance:", INSURANCE))

    for file_path in gather_targets(args.path):
        try:
            report = process_letter(file_path, insurance)
        except Exception as e:
            log.error("  ! %s: %s", file_path.name, e)
            continue
        out_path = write_report(file_path.stem, report)
        v = report.get("validation", {})
        if report.get("status") == "needs_review" or not v:
            status = "REVIEW"
        elif v.get("failed") or v.get("errors"):
            status = "FAIL"
        elif v.get("needs_review"):
            status = "REVIEW"
        else:
            status = "PASS"
        log.info("[%s] %s  (%.3fs)  -> %s",
                 status, file_path.name, report.get("execution_seconds", 0), out_path)


if __name__ == "__main__":
    main()