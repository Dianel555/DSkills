"""
PDF下载器: Unpaywall + scihub-cli
"""

import json
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional, Tuple

from . import (
    UNPAYWALL_URL, USER_AGENT, LITERATURE_EMAIL, UVX_FALLBACK_CMD,
    generate_random_email, unique_path, safe_filename,
)


class Downloader:
    """PDF 下载器（Unpaywall + scihub-cli）。"""

    @staticmethod
    def _download_with_url(url: str, outdir: Path, filename_base: str,
                           timeout: int = 60, email: str = None) -> Tuple[bool, Optional[str], Optional[str]]:
        """直接从URL下载PDF"""
        try:
            headers = {"User-Agent": USER_AGENT}
            if email:
                headers["From"] = email

            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                content_type = resp.headers.get("Content-Type", "")
                if "pdf" not in content_type.lower() and "octet-stream" not in content_type.lower():
                    return False, url, f"非PDF: {content_type}"

                data = resp.read()
                if len(data) < 1000 or data[:4] != b"%PDF":
                    return False, url, "内容不是有效PDF"

                outdir.mkdir(parents=True, exist_ok=True)
                target = unique_path(outdir / f"{filename_base}.pdf")
                with open(target, "wb") as f:
                    f.write(data)
                return True, str(target), None
        except Exception as e:
            return False, url, str(e)

    @staticmethod
    def _unpaywall_doi(doi: str, outdir: Path, filename_base: str,
                       email: str, timeout: int = 60) -> Tuple[bool, Optional[str], Optional[str]]:
        """通过Unpaywall获取免费PDF"""
        try:
            url = f"{UNPAYWALL_URL}/{doi}?email={email}"
            req = urllib.request.Request(url)
            req.add_header("User-Agent", USER_AGENT)

            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            oa = data.get("best_oa_location")
            if not oa:
                return False, None, "无开放获取版本"

            pdf_url = oa.get("url_for_pdf") or oa.get("url")
            if not pdf_url:
                return False, None, "无PDF链接"

            return Downloader._download_with_url(pdf_url, outdir, filename_base, timeout, email)
        except Exception as e:
            return False, None, f"Unpaywall错误: {e}"

    @staticmethod
    def _scihub_fallback(doi: str, outdir: Path, filename_base: str,
                         timeout: int = 180) -> Tuple[bool, Optional[str], Optional[str]]:
        """通过scihub-cli下载"""
        cmd = None
        if shutil.which("scihub-cli"):
            cmd = ["scihub-cli"]
        elif shutil.which("uvx"):
            cmd = UVX_FALLBACK_CMD.copy()
        else:
            return False, None, "scihub-cli未安装"

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            input_file = tmp / "input.txt"
            input_file.write_text(f"{doi}\n")
            tmp_out = tmp / "out"
            tmp_out.mkdir()

            full_cmd = cmd + [str(input_file), "-o", str(tmp_out), "-t", "30", "-r", "2", "-p", "1"]
            try:
                proc = subprocess.run(full_cmd, capture_output=True, text=True,
                                      timeout=timeout, check=False)
            except subprocess.TimeoutExpired:
                return False, None, "scihub超时"
            except Exception as e:
                return False, None, f"scihub执行错误: {e}"

            pdfs = list(tmp_out.rglob("*.pdf"))
            if not pdfs:
                return False, None, "scihub未返回PDF"

            best = max(pdfs, key=lambda p: p.stat().st_size)
            if best.read_bytes()[:4] != b"%PDF":
                return False, None, "无效PDF"

            outdir.mkdir(parents=True, exist_ok=True)
            target = unique_path(outdir / f"{filename_base}.pdf")
            shutil.copy2(best, target)
            return True, str(target), None

    @staticmethod
    def download_by_doi(doi: str, outdir: str = "./downloads", email: str = None,
                        scihub_fallback: str = "auto",
                        timeout: int = 120) -> dict:
        """通过DOI下载PDF (Unpaywall → scihub)"""
        outdir = Path(outdir)
        email = email or LITERATURE_EMAIL or generate_random_email()
        filename_base = safe_filename(doi, "paper")

        # 1) Unpaywall
        success, path_or_url, err = Downloader._unpaywall_doi(
            doi, outdir, filename_base, email, timeout
        )
        if success:
            return {"doi": doi, "status": "downloaded", "source": "unpaywall", "path": path_or_url}

        # 2) SciHub fallback
        if scihub_fallback != "off":
            success, path, err2 = Downloader._scihub_fallback(doi, outdir, filename_base, timeout)
            if success:
                return {"doi": doi, "status": "downloaded", "source": "scihub", "path": path}
            return {"doi": doi, "status": "failed", "unpaywall_error": err, "scihub_error": err2}

        return {"doi": doi, "status": "failed", "error": err}
