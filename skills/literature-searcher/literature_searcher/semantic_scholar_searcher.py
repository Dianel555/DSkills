"""
Semantic Scholar API 搜索
"""

import json
import urllib.error
import urllib.parse
import urllib.request
import time
from typing import List, Optional

from . import SEMANTIC_SCHOLAR_API, USER_AGENT, SEMANTIC_SCHOLAR_API_KEY, Paper


class SemanticScholarSearcher:
    """Semantic Scholar API 搜索"""

    @staticmethod
    def search(query: str, limit: int = 20, year_from: Optional[int] = None,
               year_to: Optional[int] = None) -> List[Paper]:
        papers = []
        try:
            params = {
                "query": query,
                "limit": min(limit, 100),
                "fields": "title,abstract,authors,year,citationCount,journal,externalIds,publicationTypes",
            }
            if year_from or year_to:
                year_range = f"{year_from or ''}-{year_to or ''}"
                params["year"] = year_range

            url = f"{SEMANTIC_SCHOLAR_API}/paper/search?{urllib.parse.urlencode(params)}"
            req = urllib.request.Request(url)
            req.add_header("User-Agent", USER_AGENT)
            if SEMANTIC_SCHOLAR_API_KEY:
                req.add_header("x-api-key", SEMANTIC_SCHOLAR_API_KEY)

            data = SemanticScholarSearcher._request_with_retry(req)
            if data is None:
                return papers

            for item in data.get("data", []):
                authors = [a.get("name", "") for a in item.get("authors", []) if a.get("name")]
                ext_ids = item.get("externalIds", {}) or {}
                doi = ext_ids.get("DOI", "")

                journal_info = item.get("journal", {}) or {}
                journal_name = journal_info.get("name", "")

                papers.append(Paper(
                    title=item.get("title", ""),
                    abstract=item.get("abstract", ""),
                    authors=authors,
                    doi=doi,
                    year=item.get("year"),
                    citations=item.get("citationCount", 0),
                    journal=journal_name,
                    source_platform="semantic_scholar",
                ))
        except Exception as e:
            print(f"[SemanticScholar] 搜索错误: {e}")

        return papers[:limit]

    @staticmethod
    def _request_with_retry(req: urllib.request.Request, max_attempts: int = 3) -> Optional[dict]:
        for attempt in range(max_attempts):
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code != 429 or attempt == max_attempts - 1:
                    print(f"[SemanticScholar] HTTP错误 {e.code}: {e.reason}")
                    return None

                retry_after = e.headers.get("Retry-After") if e.headers else None
                try:
                    delay = float(retry_after) if retry_after else 2 ** attempt
                except ValueError:
                    delay = 2 ** attempt
                print(f"[SemanticScholar] 配额已用尽，{delay:.0f} 秒后重试...")
                time.sleep(delay)

        return None
