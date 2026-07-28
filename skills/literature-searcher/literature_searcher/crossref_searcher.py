"""
CrossRef API 搜索
"""

import json
import re
import urllib.parse
import urllib.request
from typing import List, Optional

from . import (
    CROSSREF_API, USER_AGENT, LITERATURE_EMAIL, Paper,
    generate_random_email, safe_int,
)


class CrossRefSearcher:
    """CrossRef API 搜索"""

    @staticmethod
    def search(query: str, limit: int = 20, year_from: Optional[int] = None,
               year_to: Optional[int] = None) -> List[Paper]:
        papers = []
        try:
            params = {
                "query": query,
                "rows": min(limit, 100),
                "mailto": LITERATURE_EMAIL or generate_random_email(),
            }
            filters = []
            if year_from:
                filters.append(f"from-pub-date:{year_from}")
            if year_to:
                filters.append(f"until-pub-date:{year_to}")
            if filters:
                params["filter"] = ",".join(filters)

            url = f"{CROSSREF_API}/works?{urllib.parse.urlencode(params)}"
            req = urllib.request.Request(url)
            req.add_header("User-Agent", USER_AGENT)

            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            for item in data.get("message", {}).get("items", []):
                authors = []
                for auth in item.get("author", []):
                    name_parts = [auth.get("given", ""), auth.get("family", "")]
                    authors.append(" ".join(p for p in name_parts if p))

                pub_date = item.get("published-print", item.get("published-online", {}))
                year = None
                if "date-parts" in pub_date and pub_date["date-parts"]:
                    year = safe_int(str(pub_date["date-parts"][0][0]))

                title_parts = item.get("title", [""])
                title = title_parts[0] if title_parts else ""
                abstract = item.get("abstract", "")
                if abstract:
                    abstract = _clean_jats(abstract).strip()

                doi = item.get("DOI", "")

                papers.append(Paper(
                    title=title,
                    abstract=abstract,
                    authors=authors,
                    doi=doi,
                    year=year,
                    citations=safe_int(str(item.get("is-referenced-by-count", 0))),
                    journal=item.get("container-title", [""])[0] if item.get("container-title") else "",
                    source_platform="crossref",
                    issn=item.get("ISSN", [""])[0] if item.get("ISSN") else None,
                ))
        except Exception as e:
            print(f"[CrossRef] 搜索错误: {e}")

        return papers[:limit]


def _clean_jats(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)
