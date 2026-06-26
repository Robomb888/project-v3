import json
import logging

from ollama import chat

log = logging.getLogger(__name__)

DEFAULT_MODEL = "qwen3:4b"


def _normalize_fields(fields):
    """Accept a list of rule dicts ({field,type,label,...}), a list of names,
    or a {name: description} dict. Return a uniform list of specs."""
    specs = []
    if isinstance(fields, dict):
        for name, desc in fields.items():
            specs.append({"name": name, "type": None, "desc": desc})
    else:
        for f in fields:
            if isinstance(f, dict):
                specs.append({"name": f["field"], "type": f.get("type"),
                    "desc": f.get("description") or f.get("label", f["field"])})
            else:
                specs.append({"name": f, "type": None, "desc": f})
    return specs


def _instruction(spec):
    name, desc, rtype = spec["name"], spec["desc"], spec["type"]
    if rtype == "boolean":
        return (f"- {name}: true if the document establishes that {desc}; "
                f"false if it establishes the opposite; null if it does not address this.")
    if rtype == "min":
        return (f"- {name}: the number for '{desc}' as a JSON number; "
                f"null if the document does not state a specific number.")
    return (f"- {name}: the exact text that states '{desc}'; null if the document does not "
            f"contain it. Do NOT substitute related or tangential text.")


def run_llm_fallback(text, fields, model: str = DEFAULT_MODEL) -> dict:
    if not fields:
        return {}

    specs = _normalize_fields(fields)
    field_lines = "\n".join(_instruction(s) for s in specs)
    key_list = ", ".join(s["name"] for s in specs)

    prompt = f"""Extract the following fields from the document below.

Return a JSON object with exactly these keys: {key_list}

For each field:
- Use the type described (a boolean, a number, or the exact supporting text).
- If the document does not contain a field's information, set it to null. Do NOT
  guess, infer, or substitute a related or tangential statement.

Fields:
{field_lines}

Document:
\"\"\"{text}\"\"\"

/no_think
"""

    try:
        response = chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            format="json",          # lenient JSON mode: avoids the strict-grammar crash
            think=False,
            keep_alive=-1,
            options={"temperature": 0},
        )
    except Exception as e:                       # Ollama 500 / connection / grammar crash
        log.warning("LLM fallback call failed (%s); leaving these fields unfilled.", e)
        return {}

    content = response["message"]["content"]
    try:
        data = json.loads(content)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        log.warning("LLM fallback returned unparseable JSON: %r", content)
        return {}