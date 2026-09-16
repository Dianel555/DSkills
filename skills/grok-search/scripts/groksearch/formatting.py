import json
import re
import sys


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


def merge_search_results(
    grok_raw: str,
    tavily_results: list[dict] | None,
    tavily_requested: bool = False,
) -> list[dict]:
    extracted = extract_json(grok_raw)
    try:
        grok_items = json.loads(extracted)
        if not isinstance(grok_items, list):
            grok_items = []
    except json.JSONDecodeError:
        grok_items = []

    # Tavily reports credit usage as a non-result entry carrying only a "usage" key.
    usage = None
    if tavily_results:
        for r in tavily_results:
            if set(r) == {"usage"}:
                usage = r["usage"]
        tavily_results = [r for r in tavily_results if set(r) != {"usage"}]

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
    elif tavily_requested:
        # Keep the top-level type a JSON array so list consumers are unaffected; disclose the
        # degradation on the first item instead of injecting a synthetic pseudo-result.
        print(
            "WARNING: Tavily extra sources were requested but returned no results; output contains Grok sources only",
            file=sys.stderr,
        )
        if merged:
            merged[0]["degraded"] = "tavily_unavailable"

    # Attach usage to the first item rather than adding an element, so the array stays
    # a list of results for downstream consumers.
    if usage and merged:
        merged[0]["tavily_usage"] = usage

    return merged
