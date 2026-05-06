"""
Small helpers that don't belong anywhere else.
"""

import re
import json


def extract_json(text: str) -> dict:
    """
    Five-layer extraction — tries the obvious stuff first,
    falls back to regex scraping if the LLM wrapped it in nonsense.
    """
    # 1. Maybe it's just valid JSON
    try:
        return json.loads(text)
    except Exception:
        pass

    # 2. Wrapped in ```json or ``` blocks
    try:
        if "```json" in text:
            return json.loads(text.split("```json")[1].split("```")[0].strip())
        elif "```" in text:
            return json.loads(text.split("```")[1].split("```")[0].strip())
    except Exception:
        pass

    # 3. First { to last }
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > 0:
            return json.loads(text[start:end])
    except Exception:
        pass

    # 4. Regex key-value scraping (last resort)
    result = {}
    tokens = re.findall(r'"([^"]+)"\s*:\s*([^,}\]]+)', text)
    for k, v in tokens:
        v = v.strip(' "')
        if v.lower() == "true":
            v = True
        elif v.lower() == "false":
            v = False
        elif v.lower() == "null":
            v = None
        elif v.isdigit():
            v = int(v)
        elif v.replace(".", "", 1).isdigit():
            v = float(v)
        result[k] = v
    if result:
        return result

    return {}


def sanitize_query(query: str) -> str:
    """Strip control chars and cap length. Basic injection defense."""
    safe = re.sub(r"[\n\r\t]", " ", query)
    return safe[:500].strip()
