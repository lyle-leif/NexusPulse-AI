"""Constrained narration: a local model fills bounded slots; a validator checks them.

Provider interface: anything with `name` and `generate_structured(prompt, schema) -> dict`.
V1 implementation: Ollama on localhost (free, offline). No paid or hosted model is used.

Validator layers (risk reduction, not a guarantee):
1. Structure: valid JSON, 1-3 sentences, cited finding ids exist, next steps from the catalogue.
2. Numbers: every number in a sentence must be derivable from the findings it cites.
3. Status ceiling: a sentence may not claim a stronger status than its weakest cited finding.
4. Direction: up/down words must agree with the sign of the cited changes.
5. Lexicon: no overclaiming words; causal wording only in hedged hypothesis sentences;
   no recommendations in the summary; no segment names that the cited findings do not contain.
On failure the model gets one retry with the failure reasons; then the template is used.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from .report import NEXT_STEPS, STATUS_RANK, next_step_ids, template_summary

PROMPT_VERSION = "narrate-0.1"
OLLAMA_URL = "http://localhost:11434"

SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "array", "minItems": 1, "maxItems": 3,
            "items": {"type": "object", "properties": {
                "text": {"type": "string"},
                "finding_ids": {"type": "array", "items": {"type": "string"}},
                "status": {"type": "string", "enum": list(STATUS_RANK)}},
                "required": ["text", "finding_ids", "status"]},
        },
        "next_steps": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "text": {"type": "string"}}, "required": ["id", "text"]}},
    },
    "required": ["summary", "next_steps"],
}

OVERCLAIM = re.compile(r"\b(prov(e|es|ed|ing)|proof|certainly|definitely|clearly|undoubtedly|obviously|guarantee[sd]?|confirm(s|ed)?)\b", re.I)
CAUSAL = re.compile(r"\b(caus(e|ed|es|ing)|because|due to|led to|lead to|result(ed|s)? in|drove|driven by|responsible for|thanks to|blame)\b", re.I)
HEDGE = re.compile(r"\b(may|might|could|possibly|perhaps|appears? to|fits)\b", re.I)
RECOMMEND = re.compile(r"\b(should|must|need to|recommend)\b", re.I)
UP = re.compile(r"\b(rose|rise|rising|increase[sd]?|grew|growth|higher|above|up|gain(ed)?|jump(ed)?|spike[sd]?)\b", re.I)
DOWN = re.compile(r"\b(fell|fall|falling|decrease[sd]?|declin(e|ed|ing)|drop(ped|s)?|lower|below|down|loss|lost|shrank)\b", re.I)
NUMBER = re.compile(r"(?<![\w.])-?\$?\d[\d,]*(?:\.\d+)?%?")


# ------------------------------------------------------------------ providers
class OllamaProvider:
    def __init__(self, model: str, url: str = OLLAMA_URL, timeout: float = 180.0):
        self.model, self.url, self.timeout = model, url, timeout
        self.name = f"ollama:{model}"
        self.digest = None

    def available(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.url}/api/tags", timeout=3) as r:
                tags = json.load(r).get("models", [])
            m = next((t for t in tags if t["name"] == self.model or t["name"].split(":")[0] == self.model), None)
            self.digest = m.get("digest") if m else None
            return m is not None
        except (urllib.error.URLError, OSError, ValueError):
            return False

    def generate_structured(self, prompt: str, schema: dict) -> dict:
        body = json.dumps({"model": self.model, "prompt": prompt, "format": schema, "stream": False,
                           "options": {"temperature": 0, "seed": 7}}).encode()
        req = urllib.request.Request(f"{self.url}/api/generate", data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            raw = json.load(r)["response"]
        return {"raw": raw, "parsed": json.loads(raw)}


# ------------------------------------------------------------------ prompt
def build_prompt(inv: dict, feedback: list[str] | None = None) -> str:
    findings = [{"finding_id": f["finding_id"], "status": f["status"], "type": f["type"], "text": f["text"]} for f in inv["findings"]]
    steps = [{"id": s["id"], "text": s["text"]} for s in next_step_ids(inv)]
    rules = [
        "Write a summary of 1 to 3 short sentences for a store owner, using ONLY the findings below.",
        "Every sentence must list the finding_ids it uses and a status equal to the weakest status among them "
        "(order from strongest to weakest: observed, attributed, associated, hypothesis).",
        "Copy numbers exactly as they appear in the cited findings. Do not compute new numbers.",
        "Never say a change caused, led to or resulted in something. A possible cause may only appear in a hypothesis sentence using 'may' or 'might'.",
        "Do not use the words proves, clearly, certainly, definitely, confirms. Do not give advice in the summary.",
        "Do not mention segments, products or reasons that are not in the cited findings.",
        "For next_steps, choose 1 to 3 items from the allowed list by id; you may shorten their wording but not add new actions.",
    ]
    p = "You write short, careful business summaries.\n\nRules:\n- " + "\n- ".join(rules)
    p += "\n\nFindings:\n" + json.dumps(findings, indent=1)
    p += f"\n\nExplanation evidence: {inv['explanation_evidence']['level']}"
    p += "\n\nAllowed next steps:\n" + json.dumps(steps, indent=1)
    if feedback:
        p += "\n\nYour previous answer was rejected for these reasons; fix them:\n- " + "\n- ".join(feedback)
    p += "\n\nAnswer with JSON only."
    return p


# ------------------------------------------------------------------ validator
def _allowed_numbers(values: list) -> set[str]:
    out: set[str] = set()

    def add_num(x: float):
        for v in {x, abs(x)}:
            for d in (0, 1, 2):
                out.add(f"{v:.{d}f}")
            out.add(f"{round(v):,}")
            out.add(f"{v:,.2f}")
            if abs(v) <= 5:  # shares and relative changes are shown as percentages
                for d in (0, 1):
                    out.add(f"{100 * v:.{d}f}")

    for v in values:
        if isinstance(v, bool) or v is None:
            continue
        if isinstance(v, (int, float)):
            add_num(float(v))
        elif isinstance(v, str):
            for n in re.findall(r"\d+(?:\.\d+)?", v):
                out.add(n.lstrip("0") or "0")
                out.add(n)
    return out


def _norm(token: str) -> str:
    return token.replace("$", "").replace("%", "").replace(",", "").lstrip("-") or "0"


def validate_narration(parsed: dict, inv: dict) -> list[str]:
    errors: list[str] = []
    by_id = {f["finding_id"]: f for f in inv["findings"]}
    summary = parsed.get("summary")
    if not isinstance(summary, list) or not 1 <= len(summary) <= 3:
        return ["summary must have 1 to 3 sentences"]
    seg_vocab = {r["segment"].lower() for d in inv["drilldown"]["dimensions"].values() for r in d["rows"]}
    for i, s in enumerate(summary, 1):
        text, ids, status = s.get("text", ""), s.get("finding_ids", []), s.get("status")
        tag = f"sentence {i}"
        if not ids or any(fid not in by_id for fid in ids):
            errors.append(f"{tag}: cites missing or unknown finding ids {ids}")
            continue
        cited = [by_id[fid] for fid in ids]
        if status not in STATUS_RANK:
            errors.append(f"{tag}: unknown status {status!r}")
            continue
        weakest = max(STATUS_RANK[f["status"]] for f in cited)
        if STATUS_RANK[status] < weakest:
            errors.append(f"{tag}: claims status '{status}' but cites a '{cited[0]['status'] if len(cited) == 1 else 'weaker'}' finding")
        # numbers
        vals = [v for f in cited for v in f["values"].values()]
        allowed = {_norm(a) for a in _allowed_numbers(vals)}
        for tok in NUMBER.findall(text):
            n = _norm(tok)
            n_alt = n.rstrip("0").rstrip(".") if "." in n else n
            if n not in allowed and n_alt not in allowed:
                errors.append(f"{tag}: number {tok} is not in the cited findings")
        # direction
        changes = [f["values"][k] for f in cited for k in ("change", "contribution") if isinstance(f["values"].get(k), (int, float))]
        if changes:
            neg = all(c < 0 for c in changes)
            pos = all(c > 0 for c in changes)
            if neg and UP.search(text) and not DOWN.search(text):
                errors.append(f"{tag}: describes an increase but the cited change is negative")
            if pos and DOWN.search(text) and not UP.search(text):
                errors.append(f"{tag}: describes a decrease but the cited change is positive")
        # lexicon
        if OVERCLAIM.search(text):
            errors.append(f"{tag}: overclaiming word '{OVERCLAIM.search(text).group(0)}'")
        if CAUSAL.search(text) and not (status == "hypothesis" and HEDGE.search(text)):
            errors.append(f"{tag}: causal wording '{CAUSAL.search(text).group(0)}' outside a hedged hypothesis")
        if RECOMMEND.search(text):
            errors.append(f"{tag}: recommendation wording '{RECOMMEND.search(text).group(0)}' in the summary")
        cited_text = " ".join(str(v) for v in vals).lower() + " " + " ".join(f["text"].lower() for f in cited)
        for seg in seg_vocab:
            if re.search(rf"\b{re.escape(seg)}\b", text.lower()) and seg not in cited_text:
                errors.append(f"{tag}: mentions '{seg}', which the cited findings do not contain")
    allowed_steps = {s["id"] for s in next_step_ids(inv)}
    for st in parsed.get("next_steps", []):
        if st.get("id") not in allowed_steps:
            errors.append(f"next step {st.get('id')!r} is not in the allowed list")
        elif CAUSAL.search(st.get("text", "")) or OVERCLAIM.search(st.get("text", "")):
            errors.append(f"next step {st.get('id')!r} adds causal or overclaiming wording")
    return errors


# ------------------------------------------------------------------ orchestration
def narrate(inv: dict, provider=None, currency: str = "USD") -> dict:
    """Return a narration record. Without a provider, or after two failed attempts, template text is used."""
    base = {"prompt_version": PROMPT_VERSION, "model": None, "attempts": 0, "validation": [], "raw": []}
    if provider is None:
        return base | {"mode": "template", "fallback": False, "summary": None}
    base |= {"model": provider.name, "model_digest": getattr(provider, "digest", None), "mode": provider.name}
    feedback = None
    for attempt in (1, 2):
        base["attempts"] = attempt
        try:
            out = provider.generate_structured(build_prompt(inv, feedback), SCHEMA)
        except Exception as e:  # noqa: BLE001 - any provider failure falls back
            base["validation"].append({"attempt": attempt, "errors": [f"provider error: {e}"]})
            break
        base["raw"].append(out["raw"])
        errors = validate_narration(out["parsed"], inv)
        base["validation"].append({"attempt": attempt, "errors": errors})
        if not errors:
            steps = [s | {"text": s["text"]} for s in out["parsed"].get("next_steps", [])]
            return base | {"fallback": False, "summary": out["parsed"]["summary"], "next_steps": steps}
        feedback = errors
    return base | {"fallback": True, "summary": None}


__all__ = ["OllamaProvider", "narrate", "validate_narration", "build_prompt", "template_summary", "NEXT_STEPS"]
