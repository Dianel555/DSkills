"""
PubMed API 搜索 (E-utilities)
"""
from __future__ import annotations

from typing import List, Optional
import sys
import xml.etree.ElementTree as ET

import urllib.request
import urllib.parse
import time
import json
from . import Paper


class PubMedSearcher:
    """PubMed E-utilities 搜索器"""

    BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    USER_AGENT = "LiteratureSearcher/1.0 (mailto:research@example.com)"

    @staticmethod
    def search(query: str, limit: int = 20, year_from: Optional[int] = None,
        year_to: Optional[int] = None) -> List[Paper]:
        papers = []
        try:
            # Step 1: esearch to get PMIDs
            esearch_params = {
                "db": "pubmed",
                "term": query,
                "retmax": min(limit, 100),
                "retmode": "json",
                "sort": "relevance",
            }
            if year_from or year_to:
                date_range = ""
                if year_from and year_to:
                    date_range = f"{year_from}:{year_to}[pdat]"
                elif year_from:
                    date_range = f"{year_from}:3000[pdat]"
                else:
                    date_range = f":{year_to}[pdat]"
                esearch_params["term"] = f"{query} AND {date_range}"

            esearch_url = f"{PubMedSearcher.BASE_URL}/esearch.fcgi?{urllib.parse.urlencode(esearch_params)}"
            req = urllib.request.Request(esearch_url, headers={"User-Agent": PubMedSearcher.USER_AGENT})
            with urllib.request.urlopen(req, timeout=30) as resp:
                esearch_data = json.loads(resp.read().decode())

            id_list = esearch_data.get("esearchresult", {}).get("idlist", [])
            if not id_list:
                return papers

            # Step 2: efetch to get details
            time.sleep(0.4)  # Rate limit: 3 req/sec

            efetch_params = {
                "db": "pubmed",
                "id": ",".join(id_list),
                "retmode": "xml",
                "rettype": "abstract",
            }
            efetch_url = f"{PubMedSearcher.BASE_URL}/efetch.fcgi?{urllib.parse.urlencode(efetch_params)}"
            req = urllib.request.Request(efetch_url, headers={"User-Agent": PubMedSearcher.USER_AGENT})
            with urllib.request.urlopen(req, timeout=30) as resp:
                xml_data = resp.read().decode()

            # Parse XML
            root = ET.fromstring(xml_data)
            for article in root.findall(".//PubmedArticle"):
                medline = article.find(".//MedlineCitation")
                if medline is None:
                    continue

                article_data = medline.find("Article")
                if article_data is None:
                    continue

                # Title
                title_elem = article_data.find("ArticleTitle")
                title = title_elem.text if title_elem is not None and title_elem.text else ""

                # Abstract
                abstract_parts = []
                abstract_elem = article_data.find("Abstract")
                if abstract_elem is not None:
                    for text_elem in abstract_elem.findall("AbstractText"):
                        if text_elem.text:
                            label = text_elem.get("Label", "")
                            if label:
                                abstract_parts.append(f"{label}: {text_elem.text}")
                            else:
                                abstract_parts.append(text_elem.text)
                abstract = " ".join(abstract_parts)

                # Authors
                author_list = []
                author_elem = article_data.find("AuthorList")
                if author_elem is not None:
                    for author in author_elem.findall("Author"):
                        last_name = author.find("LastName")
                        fore_name = author.find("ForeName")
                        if last_name is not None and last_name.text:
                            if fore_name is not None and fore_name.text:
                                initials = "".join([n[0] for n in fore_name.text.split() if n])
                                author_list.append(f"{last_name.text} {initials}")
                            else:
                                author_list.append(last_name.text)

                # Journal
                journal_elem = article_data.find("Journal")
                journal = ""
                if journal_elem is not None:
                    title_elem = journal_elem.find("Title")
                    if title_elem is not None and title_elem.text:
                        journal = title_elem.text

                # Year
                year = 0
                pub_date_elem = article_data.find(".//PubDate")
                if pub_date_elem is not None:
                    year_elem = pub_date_elem.find("Year")
                    if year_elem is not None and year_elem.text:
                        try:
                            year = int(year_elem.text)
                        except ValueError:
                            pass

                # DOI
                doi = ""
                article_id_list = article.find(".//ArticleIdList")
                if article_id_list is not None:
                    for id_elem in article_id_list.findall("ArticleId"):
                        if id_elem.get("IdType") == "doi" and id_elem.text:
                            doi = id_elem.text
                            break

                # PMID
                pmid = ""
                pmid_elem = medline.find("PMID")
                if pmid_elem is not None and pmid_elem.text:
                    pmid = pmid_elem.text

                papers.append(Paper(
                    title=title,
                    abstract=abstract,
                    authors=author_list,
                    doi=doi,
                    year=year,
                    journal=journal,
                    source_platform="pubmed",
                    url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
                ))

        except Exception as e:
            print(f"[PubMed] 搜索错误: {e}", file=sys.stderr)

        return papers[:limit]
