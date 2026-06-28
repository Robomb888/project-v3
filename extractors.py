"""
extractors.py
Return type
matches the rule type:
    boolean - True or None
    min     - an int or None
    exists  - the matching text or None
"""
import re
from datetime import date
from dateutil.parser import parse

from utilities import sentences



# shared matchers (used by the keyword-anchored fields)
def _both(text, topic, verb):
    """True if one sentence matches BOTH patterns; else None."""
    for s in sentences(text):
        if topic.search(s) and verb.search(s):
            return True
    return None


def _any_of(text, patterns):
    """True if one sentence matches ANY pattern; else None."""
    for s in sentences(text):
        if any(p.search(s) for p in patterns):
            return True
    return None
  
def _find_all(text, patterns):
    result = ''
    for s in sentences(text):
        if all(p.search(s) for p in patterns):
            result=result+(s.strip())+" "
    return result

def _first_sentence(text, good_patterns, bad_patterns=[]):
    """First sentence matching ALL patterns (for `exists` fields); else None."""
    for s in sentences(text):
        if (all(p.search(s) for p in good_patterns)) and (all(p.search(s) is None for p in bad_patterns)):
            return s.strip()
    return None


_DURATION = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:continuous|consecutive|full|total|straight)?\s*(year|yr|month|mo)s?\b", re.I)


def _months_near(text, anchor):
    """Exactly one unambiguous duration near `anchor` -> months; else None."""
    found = set()
    for s in sentences(text):
        if not anchor.search(s):
            continue
        for m in _DURATION.finditer(s):
            n, unit = float(m.group(1)), m.group(2).lower()
            months = n * 12 if unit.startswith(("year", "yr")) else n
            if 0 < months <= 1200:
                found.add(int(round(months)))
    return found.pop() if len(found) == 1 else None



# routing critical (original)
def _extract_dob(text):
    patterns = [
        r'(?:date of birth|dob)\s*[:\-]?\s*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4})',
        r'(?:date of birth|dob)\s*[:\-]?\s*([A-Za-z]+\s+\d{1,2},?\s+\d{4})',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def age(text):
    dob_text = _extract_dob(text)
    if dob_text is not None:
        dob = parse(dob_text).date()
        today = date.today()
        years = today.year - dob.year
        if (today.month, today.day) < (dob.month, dob.day):
            years -= 1
        return years
    return None


def surgery_type(text):
    text = text.lower()
    if any(p in text for p in ["phalloplasty", "metoidioplasty", "vaginoplasty", "bottom surgery", "orchiectomy"]):
        return "bottom"
    elif any(p in text for p in ["mastectomy", "top surgery", "breast reduction", "chest surgery"]):
        return "mastectomy"
    elif any(p in text for p in ["breast augmentation", "augmentation"]):
        return "breast_aug"
    elif any(p in text for p in ["facial feminization", "facial masculinization", "facial gender-affirming surgery", "facial surgery"]):
        return "facial"
    return None



# original keyword booleans

def capacity_for_informed_decision(text):
    text = text.lower()
    if any(p in text for p in [
        "capacity to make an informed decision", "informed consent", "informed decision",
        "sound judgement", "decision-making capacity", "informed healthcare decision", "informed medical decision"
    ]):
        return True
    return None


def diagnosed_gender_dysphoria(text):
    t = text.lower()
    return True if ("gender dysphoria" in t) or ("gender incongruence" in t) else None


def understands_risks(text):
    text = text.lower()
    if any(p in text for p in [
        "understands risks", "understands the risks", "understanding of the risks",
        "discussed the risks", "risks and benefits", "benefits and risks",
        "potential complications", "informed of the risks", "adverse effects",
        "possible complications", "irreversible effects",
    ]):
        return True
    return None

    re.compile(r"\b(understand\w*|discuss\w*|inform\w*)\s(of)?(the)?(potential)?\w*(risks?|effects?|complications?)\b", re.I)


def favorable_psychosocial_behavioral_eval(text):
    return _both(text,
        re.compile(r"\b(reason\w+|well|adaquat\w+|stabl\w+)\b", re.I),
        re.compile(r"\b(control\w+|stabl\w+|managed|hous\w+)\b", re.I))



# clinician original

_SIGNOFF = ["sincerely", "regards", "respectfully",
            "best"]
# Degrees as bounded tokens (optional periods/spaces) so a sign-off's "Dr." cannot
# hide them and substrings inside words (e.g. "do" in "doctor") do not false match.
_DEGREE_RE = re.compile(
    r"\b(ph\.?\s?d|psy\.?\s?d|m\.?\s?s\.?\s?w|m\.?\s?s\.?\s?n|pmhnp|ed\.?\s?d|"
    r"d\.?\s?w\.?\s?m|m\.?\s?d|m\.?\s?a|m\.?\s?ed|m\.?\s?s|d\.?\s?o)", re.I)
_LIC_RE = re.compile(
    r"(l\.?p|lc?pc|li?csw|lgsw|lmft|lmsw|lc?mhc|cmhc|lpc?c)\b", re.I)
 
 
def clinician_masters_degree_or_above(text):       # was clinician.extract
    t = text
    # Look for a degree token in the ~120 chars AFTER each sign-off, not within the
    # same split-sentence: "Sincerely, Dr. Jane Lee, PhD" splits on "Dr." and would
    # otherwise separate the sign-off from the degree, missing it.
    for m in re.finditer("|".join(re.escape(k) for k in _SIGNOFF), t, re.I):
        deg = _DEGREE_RE.search(t[m.start(): m.start() + 120])
        lic = _LIC_RE.search(t[m.start(): m.start() + 120])
        if deg:
            if lic:
                return deg.group(1), lic.group(1)
            return deg.group(1)
    return None


_CLIN_PROFESSION = (r"(?:clinical\s+)?(?:psychologist|psychiatrist|social\s+worker|"
                    r"counselor|therapist|mental\s+health\s+(?:nurse|practitioner)|"
                    r"marriage\s+and\s+family\s+therapist|nurse\s+practitioner)")
_CLIN_CRED = [
    re.compile(r"(licen[sc]ed\s+" + _CLIN_PROFESSION + r"(?:\s*\([^)]*\))?)", re.IGNORECASE),
    re.compile(r"(licen[sc]e\s*(?:#|number|no\.?)?\s*[:#]?\s*[A-Z0-9-]{4,})", re.IGNORECASE),
    re.compile(r"\b([A-Z]{2,4}\s?#?\s?[A-Z]{0,3}\s?\d{3,7})\b"),
]


def clinician_credentials_from_licensing_board(text):
    for pat in _CLIN_CRED:
        m = pat.search(text)
        if m:
            return m.group(1).strip()
    return None


_CLIN_EXPERIENCE = (r"(?:experience|training|expertise|knowledge|specializ\w+|"
                    r"competen\w+|years?\s+(?:of\s+)?(?:work|practice|treating))")
_CLIN_GENDER = (r"(?:gender\s+dysphoria|gender[-\s]?nonconforming|transgender|"
                r"gender[-\s]?affirming|gender\s+identity|gender\s+health|lgbtq)")


def clinician_experience_in_gender_dysphoria(text):     # was clinician.extract_experience
    for sent in sentences(text):
        if re.search(_CLIN_EXPERIENCE, sent, re.IGNORECASE) and re.search(_CLIN_GENDER, sent, re.IGNORECASE):
            return sent.strip()
    return None



# hormone_duration_months original)

_HRT_KEYWORDS = ("testosterone", "estrogen", "estradiol", "hormone", "hrt",
                 "masculinizing", "feminizing", "trt", "gnrh")
_HRT_HORMONE = r"(?:testosterone|estrogen|estradiol|hormone\w*|hrt|trt|masculiniz\w*|feminiz\w*|gnrh)"
_HRT_CUE = (r"(?:for|over|during|starting)\s+"
            r"(?:the\s+|past\s+|over\s+|about\s+|approximately\s+|nearly\s+|almost\s+|"
            r"more\s+than\s+|at\s+least\s+)*")
_HRT_NEAR = _HRT_HORMONE + r"\b[^.\n]{0,40}?" + _HRT_CUE
_HRT_YEARS = re.compile(
    _HRT_NEAR + r"(\d+)\s*(?:years?|yrs?)(?:[\s,]+(?:and\s+)?(\d+)\s*(?:months?|mos?))?", re.IGNORECASE)
_HRT_MONTHS = re.compile(_HRT_NEAR + r"(\d+)\s*(?:months?|mos?)", re.IGNORECASE)
_HRT_DATE = re.compile(
    r"(?:since|started|initiated|began|commenced|starting)\b[^.\n]{0,40}?" + _HRT_HORMONE +
    r"?[^.\d\n]{0,40}?((?:[A-Za-z]{3,9}\s+)?\d{4}|\d{1,2}[/-]\d{4}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
    re.IGNORECASE)


def _hrt_date_months(text):
    m = _HRT_DATE.search(text)
    if not m:
        return None
    try:
        start = parse(m.group(1), fuzzy=True).date()
    except (ValueError, OverflowError):
        return None
    today = date.today()
    months = (today.year - start.year) * 12 + (today.month - start.month)
    return months if 0 < months <= 1200 else None


def hormone_duration_months(text):
    all_durations, date_based = set(), None
    for sentence in (s for s in sentences(text) if any(k in s.lower() for k in _HRT_KEYWORDS)):
        for m in _HRT_YEARS.finditer(sentence):
            all_durations.add(int(m.group(1)) * 12 + (int(m.group(2)) if m.group(2) else 0))
        for m in _HRT_MONTHS.finditer(sentence):
            all_durations.add(int(m.group(1)))
        if date_based is None:
            date_based = _hrt_date_months(sentence)
    if len(all_durations) == 1:
        v = next(iter(all_durations))
        return v if 0 < v <= 1200 else None
    if len(all_durations) > 1:
        return None
    return date_based



# months_living_as_identified_gender original

_LIV_ANCHOR = (r"(?:liv(?:ing|ed)(?:\s+full[-\s]?time)?\s+(?:as|in)|"
               r"full[-\s]?time\s+(?:as|in)|social(?:ly)?\s+transition\w*|transition\w*|"
               r"real[-\s]?life\s+experience|presenting\s+as|gender\s+role)")
_LIV_CUE = (r"(?:for|over|during|of)\s+"
            r"(?:the\s+|past\s+|over\s+|about\s+|approximately\s+|nearly\s+|almost\s+|"
            r"more\s+than\s+|at\s+least\s+)*")
_LIV_NEAR = _LIV_ANCHOR + r"[^.\n]{0,30}?" + _LIV_CUE
_LIV_YEARS = re.compile(
    _LIV_NEAR + r"(\d+)\s*(?:years?|yrs?)(?:[\s,]+(?:and\s+)?(\d+)\s*(?:months?|mos?))?", re.IGNORECASE)
_LIV_MONTHS = re.compile(_LIV_NEAR + r"(\d+)\s*(?:months?|mos?)", re.IGNORECASE)
_LIV_AGO_YEARS = re.compile(_LIV_ANCHOR + r"[^.\d\n]{0,20}?(\d+)\s*(?:years?|yrs?)\s+ago", re.IGNORECASE)
_LIV_AGO_MONTHS = re.compile(_LIV_ANCHOR + r"[^.\d\n]{0,20}?(\d+)\s*(?:months?|mos?)\s+ago", re.IGNORECASE)
_LIV_DATE = re.compile(
    _LIV_ANCHOR + r"[^.\d\n]{0,30}?(?:since|in|on|from)\s+"
    r"((?:[A-Za-z]{3,9}\s+)?\d{4}|\d{1,2}[/-]\d{4}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", re.IGNORECASE)


def _liv_date_months(text):
    m = _LIV_DATE.search(text)
    if not m:
        return None
    try:
        start = parse(m.group(1), fuzzy=True).date()
    except (ValueError, OverflowError):
        return None
    today = date.today()
    months = (today.year - start.year) * 12 + (today.month - start.month)
    return months if 0 < months <= 1200 else None


def months_living_as_identified_gender(text):
    durations = set()
    for m in _LIV_YEARS.finditer(text):
        durations.add(int(m.group(1)) * 12 + (int(m.group(2)) if m.group(2) else 0))
    for m in _LIV_MONTHS.finditer(text):
        durations.add(int(m.group(1)))
    for m in _LIV_AGO_YEARS.finditer(text):
        durations.add(int(m.group(1)) * 12)
    for m in _LIV_AGO_MONTHS.finditer(text):
        durations.add(int(m.group(1)))
    durations = {d for d in durations if 0 < d <= 1200}
    if len(durations) == 1:
        return next(iter(durations))
    if len(durations) > 1:
        return None
    return _liv_date_months(text)



# plan_for_follow_up (original)

_FOLLOWUP = re.compile(
    r"(?:follow[-\s]?up|see\s+(?:the\s+patient|him|her|them|me)\s+(?:again|in|for)|"
    r"return\s+(?:visit|in\s+\d|for\s+a)|schedul\w+\s+(?:a\s+)?(?:follow|appointment|visit)|"
    r"post[-\s]?operative\s+(?:care|visit|appointment|monitoring)|after[-\s]?care|"
    r"ongoing\s+(?:care|monitoring|support|treatment)|continue\s+to\s+(?:see|monitor|follow|provide)|"
    r"monitor\w*\s+(?:post|after|recovery|progress))", re.IGNORECASE)


def plan_for_follow_up(text):
    return True if _FOLLOWUP.search(text) else None



# new fields - boolean (topic, verb in one sentence)

def gender_dysphoria_marked_and_sustained(text):
    return _both(text,
        re.compile(r"\b(gender\s+dysphoria|gender\s+incongruen\w+|dysphoria|incongruen\w+)\b", re.I),
        re.compile(r"\b(marked|persistent|long-?standing|longstanding|chronic|sustained|well-?documented|since\s+(childhood|early|adolescen))\b", re.I))

def other_causes_excluded(text):
    return _both(text,
        re.compile(r"\b(rule[d]?\s+out|exclud\w+|no\s+other\s+(cause|explanation)|other\s+(possible\s+)?cause|alternative\s+(cause|explanation)|differential)\b", re.I),
        re.compile(r"\b(gender|dysphoria|incongruen\w+)\b", re.I))


def comorbid_conditions_assessed(text):
    result=""
    result +=_first_sentence(text, [re.compile(p, re.I) for p in (
        r"\b(mental\s+health|psychiatric|psychological|medical\s+condition|comorbid\w*|co-?occurring|co-?existing|other\s+condition|concerns?|)\b",
        r"\b(assess\w*|evaluat\w*|address\w*|review\w*|consider\w*|screen\w*)?\b",
        r"\b(procedure|surgery|operation|treatment|intervention|goals?)?\b",
        r"\b(affect(s|ed|ing)?|impact(s|ed|ing)?|interfere(s|d|ing)?(\s+with)?|prevent(s|ed|ing)?|compromise(s|d|ing)?)\b")])

def significant_concerns_well_controlled(text):
    return _first_sentence(text, [re.compile(p, re.I) for p in (
        r"\b(mental\s+health|psychiatric|medical|behavioral|comorbid\w*|concern|condition|depress\w*|anxiety|mood|disorder|illness|symptom|PTSD|bipolar|substance)\b",
        r"\b(well[\s-]?controlled|reasonably\s+(well\s+)?controlled|stable|in\s+(stable\s+)?remission|managed|adequately\s+(managed|controlled))\b")])

def understands_reproductive_effects(text):
    return _both(text,
        re.compile(r"\b(reproduc\w+|fertilit\w+|sperm|egg|oocyte|gamete|biological\s+child\w*|family\s+planning|sterili\w+)\b", re.I),
        re.compile(r"\b(discuss\w*|inform\w*|advis\w*|counsel\w*|understand\w*|explor\w*|aware|educat\w*|review\w*)\b", re.I))

def informed_consent_obtained(text):
    return _both(text,
        re.compile(r"\binformed\s+consent\b", re.I),
        re.compile(r"\b(obtain\w*|secured|provid\w*|given|gave|documented|signed|has\s+been)\b", re.I))

def clinician_available_for_coordination(text):
    return _both(text,
        re.compile(r"\bcoordinat\w*\b", re.I),
        re.compile(r"\b(available|care|surgeon|team|treatment|post-?op\w*|peri-?op\w*)\b", re.I))

def emotional_cognitive_maturity_for_consent(text):
    return _both(text,
        re.compile(r"\b(maturity|mature|emotional\w*|cognitive\w*|developmental)\b", re.I),
        re.compile(r"\b(consent|assent|inform\w*|decision|capac\w*)\b", re.I))

def diagnostic_assessment_included(text):
    return _both(text,
        re.compile(r"\b(diagnostic\s+assessment|psychosocial\s+assessment|comprehensive\s+assessment)\b", re.I),
        re.compile(r"\b(complet\w*|includ\w*|attach\w*|perform\w*|conduct\w*|provid\w*|enclos\w*|recent)\b", re.I))

def clinical_rationale_for_surgery(text):
    return _find_all(text, [re.compile(p, re.I) for p in (
        r"\b(rationale|clinical\s+reasoning|justification|recommend\w*|support\w*)\b",
        r"\b(surger\w*|surgical|procedure|treatment|request)\b")])

def irreversibility_acknowledged(text):
    return _both(text,
        re.compile(r"\b(irreversib\w+|permanen\w+|cannot\s+be\s+(undone|reversed)|not\s+reversible)\b", re.I),
        re.compile(r"\b(surger\w*|procedure|treatment|effect|inform\w*|understand\w*|aware|acknowledg\w*)\b", re.I))

def clinician_interdisciplinary_engagement(text):
    return _both(text,
        re.compile(r"\b(engage\w*|liaise\w*|consult\w*|collaborat\w*|coordinat\w*|refer\w*|communicat\w*)\b", re.I),
        re.compile(r"\b(disciplin\w*|other\s+(provider|professional|clinician)s?|colleague|multidisciplinary|transgender\s+health)\b", re.I))

def clinician_part_of_gender_team(text):
    return _both(text,
        re.compile(r"\bgender\s+(care\s+)?(team|clinic|program|service)\b", re.I),
        re.compile(r"\b(part\s+of|member\s+of|on\s+the|belong|work(s|ing)?\s+(with|on)|our)\b", re.I))

def unequivocal_support_for_procedure(text):
    return _both(text,
        re.compile(r"\b(unequivocal\w*|unreserved\w*|without\s+reservation|wholeheartedly|strong\w*|full[ly]*)\b", re.I),
        re.compile(r"\b(support|recommend|endorse)\w*\b", re.I))

def medical_management_compliance(text):
    return _both(text,
        re.compile(r"\b(compli\w*|adher\w*|follow\w*|consistent\w*|engag\w*|attend\w*)\b", re.I),
        re.compile(r"\b(treatment|management|recommend\w*|regimen|appointment|therapy|medication|care)\b", re.I))

def breast_cancer_risk_assessed(text):
    return _both(text,
        re.compile(r"\bbreast\s+cancer\b", re.I),
        re.compile(r"\b(risk|assess\w*|evaluat\w*|screen\w*|review\w*|family\s+history)\b", re.I))

def appropriate_hormone_use(text):
    return _both(text,
        re.compile(r"\b(hormone\w*|HRT|GAHT|testosterone|estrogen|estradiol|masculiniz\w*|feminiz\w*)\b", re.I),
        re.compile(r"\b(appropriate|stable|adherent|managed|continu\w*|ongoing|toler\w*|respond\w*|well)\b", re.I))

def comprehensive_assessment_completed(text):
    return _both(text,
        re.compile(r"\b(comprehensive|thorough|complete|full|extensive)\b", re.I),
        re.compile(r"\b(assessment|evaluation|diagnostic)\b", re.I))

def clinician_qualified_competencies(text):
    return _both(text,
        re.compile(r"\b(competen\w*|qualified|trained|expertise|skilled)\b", re.I),
        re.compile(r"\b(transgender|gender\s+diverse|gender\s+dysphoria|TGD|gender-affirming|assessment)\b", re.I))

def parental_or_guardian_consent(text):
    return _both(text,
        re.compile(r"\b(parent\w*|guardian\w*|mother|father|legal\s+guardian|caregiver)\b", re.I),
        re.compile(r"\b(consent\w*|approv\w*|agree\w*|authoriz\w*|support\w*|involv\w*|present)\b", re.I))



# new fields - boolean (any pattern)

def nicotine_free_or_abstained(text):
    return _any_of(text, [re.compile(p, re.I) for p in (
        r"\b(never\s+(smoked|a\s+smoker|used\s+(tobacco|nicotine)))\b",
        r"\b(non-?smoker|tobacco-?free|nicotine-?free|smoke-?free)\b",
        r"\b(denies|no\s+(history\s+of\s+)?)\s*(tobacco|nicotine|smoking)\b",
        r"\b(abstain\w*|quit|ceased|stopped)\s+(from\s+)?(smoking|tobacco|nicotine)\b")])

def no_medical_contraindications(text):
    return _any_of(text, [re.compile(p, re.I) for p in (
        r"\bno\s+(medical\s+)?contraindication", r"\bwithout\s+contraindication",
        r"\bmedically\s+(cleared|appropriate|stable|fit)\b",
        r"\bno\s+medical\s+(barrier|concern|reason)\b")])

def social_transition_or_unnecessary(text):
    return _any_of(text, [re.compile(p, re.I) for p in (
        r"(social\w*\s+transition\w*|socially\s+transition\w*|name\s+change|pronoun|presents?\s+as|living\s+(as|in|full-?time)|real-?life\s+(experience|role))",
        r"\btransition[^.]{0,40}(unnecessary|not\s+(necessary|required|applicable))")])

def meets_recognized_clinical_criteria(text):
    return _any_of(text, [re.compile(p, re.I) for p in (
        r"\bWPATH\b", r"\bWorld\s+Professional\s+Association\b", r"\bstandards\s+of\s+care\b",
        r"\bSOC-?\s?8\b", r"\b(established|recognized|clinical)\s+(criteria|guidelines)\b")])

def multidisciplinary_team_involved(text):
    return _any_of(text, [re.compile(p, re.I) for p in (
        r"\bmultidisciplinary\b", r"\binter-?disciplinary\b",
        r"\bgender\s+(care\s+)?team\b", r"\b(treatment|care)\s+team\b")])



# new fields - exists (return matching sentence)

def second_independent_clinician_letter(text):
    return _first_sentence(text, [re.compile(p, re.I) for p in (
        r"\b(second|two|2|additional|independent)\b",
        r"\b(letter|opinion|assessment|clinician|provider|evaluation|referral)\b")])

def clinical_relationship_duration_described(text):
    return _first_sentence(text, [re.compile(p, re.I) for p in (
        r"\b(seen|treating|treated|known|work\w*\s+with|in\s+(therapy|treatment|my\s+care)|patient\s+(for|since)|established\s+(care|relationship)|relationship)\b",
        r"(\b\d+\s*(year|yr|month|mo|week)s?\b|since\s+\w*\s*\d{4}|over\s+the\s+(past|last))")],
        
        [re.compile(p, re.I) for p in (_CLIN_EXPERIENCE, _CLIN_GENDER,)])

def gender_identifying_characteristics_described(text):
    return _find_all(text, [re.compile(p, re.I) for p in (
        r"\b(identifies\s+as|gender\s+identity|affirmed\s+(male|female|gender)|presents?\s+as|gender\s+(presentation|expression)|transgender\s+(man|woman|male|female)|assigned\s+(male|female)\s+at\s+birth|AMAB|AFAB)\b",)])

_DIAG_RE = [re.compile(p, re.I) for p in (
        r"\b(diagnos\w+|assessment\s+(result|finding)s?|DSM-?5?|ICD-?10?|F\.?64|meets\s+(the\s+)?criteria)\b",
        r"\b(gender\s+dysphoria|gender\s+incongruen\w+|F\.?64|disorder|phobia|alcohol|abuse|nicotine|schizo\w+|psych\w+|depress\w+|anxiety|PTSD|ADHD)\b")]

def assessment_results_with_diagnoses(text):
    return _find_all(text, _DIAG_RE)


def assessment_results_with_diagnoses_old(text): 
    return _first_sentence(text, _DIAG_RE,
        [re.compile(p, re.I) for p in (
        _CLIN_EXPERIENCE,
        _CLIN_GENDER)])



# new fields - min (months)

def psychotherapy_duration_months(text):
    return _months_near(text, re.compile(r"\b(psychotherapy|therapy|counsel\w+|sessions|treatment\s+with)\b", re.I))

def behavioral_health_remission_months(text):
    return _months_near(text, re.compile(r"\b(remission|sober|abstinen\w+|in\s+recovery|relapse-?free|clean)\b", re.I))

_WAIVE_HRT = re.compile(r"\b(hormone\w*|hrt|gaht|testosterone|estrogen|estradiol|masculiniz\w*|feminiz\w*)\b", re.I)
_WAIVE_ND1 = re.compile(
    r"(declin\w+|"
    r"(do(es)?|did)\s+not\s+(desire|wish|want|seek|pursu\w+|intend|plan)|"
    r"not\s+(seeking|pursuing|interested\s+in|planning|desir\w+|want\w+|wish\w+)|"
    r"(has|have|with)\s+no\s+(desire|wish|interest|intention|plan)|"
    r"no\s+(desire|wish|interest|intention|plan)\s+(for|to|in))"
    r"\s+(to\s+(take|start|use|begin|pursue|initiate|continue)\s+|(any\s+)?(further\s+)?(ongoing\s+)?)?"
    r"(hormone|hrt|gaht|testosterone|estrogen|estradiol|masculiniz\w*|feminiz\w*)", re.I)
_WAIVE_ND2 = re.compile(
    r"(hormone\w*|hrt|gaht|testosterone|estrogen|estradiol)\b[^.]{0,40}?"
    r"((is|are|was|were)\s+not\s+(desired|wanted|wished|sought|of\s+interest)|not\s+being\s+pursued)", re.I)
_WAIVE_CONTRA = re.compile(
    r"((is|are|was|were|been|remains?|medically)\s+contraindicated|"
    r"contraindicated\s+(for|due|because|in)|"
    r"(cannot|can't|unable\s+to)\s+(safely\s+)?(take|tolerate|use|start|receive)\s+(\w+\s+){0,2}(hormone|hrt|gaht|testosterone|estrogen|estradiol)|"
    r"medically\s+(unable|inadvisable))", re.I)
_WAIVE_NEG = re.compile(r"\b(no|not|without|aren'?t|isn'?t|are\s+not|is\s+not)\s+(\w+\s+){0,3}contraindicat", re.I)
 
 
def hormones_not_desired_or_contraindicated(text):
    """True if the letter states hormones are not desired or are medically
    contraindicated (waives the hormone-duration requirement); else None."""
    for s in sentences(text):
        if not _WAIVE_HRT.search(s):
            continue
        if _WAIVE_ND1.search(s) or _WAIVE_ND2.search(s):
            return True
        if _WAIVE_CONTRA.search(s) and not _WAIVE_NEG.search(s):
            return True
    return None