"""
Scopus API 搜索
"""

import json
import urllib.parse
import urllib.request
from typing import List, Optional

from . import (
    SCOPUS_API, USER_AGENT, ELSEVIER_API_KEY, SCOPUS_API_KEY, Paper,
    safe_int,
)


class ScopusSearcher:
    """Scopus API 搜索器"""

    @staticmethod
    def search(query: str, limit: int = 20, year_from: Optional[int] = None,
               year_to: Optional[int] = None, api_key: Optional[str] = None) -> List[Paper]:
        api_key = api_key or ELSEVIER_API_KEY or SCOPUS_API_KEY
        if not api_key:
            print("[Scopus] 需要ELSEVIER_API_KEY，跳过")
            return []

        papers = []
        try:
            params = {
                "query": query,
                "count": min(limit, 25),
            }
            if year_from or year_to:
                yf = year_from or ""
                yt = year_to or ""
                params["date"] = f"{yf}-{yt}"

            url = f"{SCOPUS_API}?{urllib.parse.urlencode(params)}"
            req = urllib.request.Request(url)
            req.add_header("User-Agent", USER_AGENT)
            req.add_header("X-ELS-APIKey", api_key)
            req.add_header("Accept", "application/json")

            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            for entry in data.get("search-results", {}).get("entry", []):
                authors = []
                if "creator" in entry:
                    authors = [entry["creator"].get("$", "")]

                papers.append(Paper(
                    title=entry.get("dc:title", ""),
                    abstract="",
                    authors=authors,
                    doi=entry.get("prism:doi", ""),
                    year=safe_int(entry.get("prism:coverDate", "")[:4]),
                    citations=safe_int(entry.get("citedby-count", "0")),
                    journal=entry.get("prism:publicationName", ""),
                    source_platform="scopus",
                    issn=entry.get("prism:issn", ""),
                ))
        except Exception as e:
            print(f"[Scopus] 搜索错误: {e}")

        return papers[:limit]
