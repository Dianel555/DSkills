"""
OpenAlex API 搜索
"""

import json
import urllib.parse
import urllib.request
from typing import List, Optional

from . import (
    OPENALEX_API, USER_AGENT, LITERATURE_EMAIL, OPENALEX_EMAIL,
    OPENALEX_API_KEY, Paper, generate_random_email, reconstruct_abstract,
    safe_int,
)


class OpenAlexSearcher:
    """OpenAlex API 搜索"""

    @staticmethod
    def search(query: str, limit: int = 20, year_from: Optional[int] = None,
               year_to: Optional[int] = None) -> List[Paper]:
        papers = []
        try:
            email = OPENALEX_EMAIL or LITERATURE_EMAIL or generate_random_email()
            params = {
                "search": query,
                "per_page": min(limit, 200),
                "mailto": email,
            }
            if year_from and year_to:
                params["filter"] = f"publication_year:{year_from}-{year_to}"
            elif year_from:
                params["filter"] = f"publication_year:>{year_from - 1}"
            elif year_to:
                params["filter"] = f"publication_year:<{year_to + 1}"
            if OPENALEX_API_KEY:
                params["api_key"] = OPENALEX_API_KEY

            url = f"{OPENALEX_API}/works?{urllib.parse.urlencode(params)}"
            headers = {"User-Agent": USER_AGENT}
            req = urllib.request.Request(url, headers=headers)

            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            for item in data.get("results", []):
                doi_raw = item.get("doi", "")
                doi = doi_raw.replace("https://doi.org/", "") if doi_raw else ""

                authorships = item.get("authorships", [])
                authors = [a.get("author", {}).get("display_name", "") for a in authorships]
                authors = [a for a in authors if a]

                abstract = reconstruct_abstract(item.get("abstract_inverted_index"))

                year = safe_int(str(item.get("publication_year", "")))

                loc = item.get("primary_location", {}) or {}
                source = loc.get("source", {}) or {}
                journal = source.get("display_name", "")

                open_access = item.get("open_access", {}) or {}
                oa_url = open_access.get("oa_url", "")
                is_oa = open_access.get("is_oa", False)

                issn_list = source.get("issn", []) or []
                issn = issn_list[0] if issn_list else None

                papers.append(Paper(
                    title=item.get("title", ""),
                    abstract=abstract,
                    authors=authors,
                    doi=doi,
                    year=year,
                    citations=item.get("cited_by_count", 0),
                    journal=journal,
                    source_platform="openalex",
                    is_oa=is_oa,
                    pdf_url=oa_url,
                    issn=issn,
                ))
        except Exception as e:
            print(f"[OpenAlex] 搜索错误: {e}")

        return papers[:limit]
