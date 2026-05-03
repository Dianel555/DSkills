import json
import re
from typing import List, Optional


def extract_json(text: str) -> str:
    match = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", text)
    if match:
        text = match.group(1).strip()

    try:
        data = json.loads(text)
        if isinstance(data, list):
            standardized = []
            for item in data:
                if isinstance(item, dict):
                    standardized.append(
                        {
                            "title": item.get("title", ""),
                            "url": item.get("url", item.get("link", "")),
                            "description": item.get(
                                "description",
                                item.get("content", item.get("snippet", item.get("summary", ""))),
                            ),
                        }
                    )
            return json.dumps(standardized, ensure_ascii=False, indent=2)
        return json.dumps(data, ensure_ascii=False, indent=2)
    except json.JSONDecodeError:
        return json.dumps({"error": "Failed to parse JSON", "raw": text[:500]}, ensure_ascii=False, indent=2)


def merge_search_results(grok_raw: str, tavily_results: Optional[List[dict]]) -> List[dict]:
    extracted = extract_json(grok_raw)
    try:
        grok_items = json.loads(extracted)
        if not isinstance(grok_items, list):
            grok_items = []
    except json.JSONDecodeError:
        grok_items = []

    seen_urls = {item.get("url", "").strip() for item in grok_items if item.get("url", "").strip()}
    merged = list(grok_items)

    if tavily_results:
        for r in tavily_results:
            url = r.get("url", "").strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            merged.append(
                {
                    "title": r.get("title", ""),
                    "url": url,
                    "description": r.get("content", ""),
                    "provider": "tavily",
                }
            )
    return merged
