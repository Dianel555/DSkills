# Literature Searcher

用于检索学术文献、下载开放获取 PDF，以及按关键词和期刊对论文分类的 Python 标准库工具包。

## 功能

- 跨平台检索：CrossRef、OpenAlex、PubMed、Semantic Scholar，以及需要 Elsevier 密钥的 Scopus
- 结果去重：优先按 DOI，否则按标题
- PDF 下载：通过 Unpaywall 获取开放获取版本；`scihub-cli` 回退需显式启用
- 论文分类：`PaperClassifier` 接受 `Paper` 对象或字典
- 增量监控：记录已见论文、输出新增论文及分类报告
- 洞察分析：统计搜索结果的来源、年份和分类覆盖度

## 运行

此工具仅使用 Python 标准库。在技能目录中运行：

```bash
cd skills/literature-searcher
python -m literature_searcher.searcher search "ionogel flexible sensor" --limit 10
python -m literature_searcher.searcher download --doi 10.1016/j.cej.2022.135593
```

配置并运行监控：

```powershell
New-Item -ItemType Directory -Force data | Out-Null
Copy-Item monitor_config.json.template data/monitor_config.json
```

在 `data/monitor_config.json` 填写 `queries` 后：

```bash
python -m literature_searcher.monitor --config data/monitor_config.json
python -m literature_searcher.insight --input data/monitor_results.json
```

搜索时可重复传入 `--platform`，并可使用 `--year-from` 和 `--year-to` 限制年份：

```bash
python -m literature_searcher.searcher search "solid electrolyte" \
  --platform openalex --platform semantic_scholar --year-from 2020
```

默认只尝试 Unpaywall。需要启用可选的 `scihub-cli` 回退时，显式传入：

```bash
python -m literature_searcher.searcher download --doi 10.1016/j.cej.2022.135593 \
  --scihub-fallback auto
```

## 配置

复制 `.env.example` 为 `.env` 并填写需要的变量。包会在初始化时从技能目录加载 `.env`，但不会覆盖已经由 shell 导出的环境变量：

| Variable | Required | Purpose |
| --- | --- | --- |
| `LITERATURE_EMAIL` | Recommended | CrossRef、OpenAlex 与 Unpaywall 使用的联系邮箱 |
| `OPENALEX_EMAIL` | Optional | 覆盖 OpenAlex 的联系邮箱 |
| `OPENALEX_API_KEY` | Optional | OpenAlex API key |
| `SEMANTIC_SCHOLAR_API_KEY` | Optional | Semantic Scholar API key |
| `ELSEVIER_API_KEY` | Scopus only | Scopus API key |
| `DEEPLX_ENDPOINT` | Monitor default translation | User-provided HTTPS DeepLX endpoint |
| `LOCAL_LLM_BASE_URL` | Local-LLM translation | OpenAI-compatible local API base URL |
| `LOCAL_LLM_MODEL` | Local-LLM translation | Model name exposed by the local service |

PowerShell 也可以临时覆盖 `.env` 中的配置：

```powershell
$env:LITERATURE_EMAIL = "you@example.com"
$env:OPENALEX_API_KEY = "..."
$env:DEEPLX_ENDPOINT = "https://translate.example.com/translate"
```

监控默认使用无需 DeepL key 的在线 DeepLX。设置 `DEEPLX_ENDPOINT` 为在线 HTTPS 端点即可。也可设置 `LOCAL_LLM_BASE_URL` 与 `LOCAL_LLM_MODEL`，并传入 `--translator local_llm` 使用本机 OpenAI 兼容服务；翻译失败不会终止检索，错误会记录在监控 JSON 输出中。

## Python API

```python
from literature_searcher.classifier import PaperClassifier
from literature_searcher.searcher import merge_and_deduplicate, search_papers

results = search_papers("ionogel sensor", platforms=["crossref", "openalex"], limit=10)
papers = merge_and_deduplicate(results)
classification = PaperClassifier().classify({"title": papers[0].title})
```

## 布局

```text
literature_searcher/
├── __init__.py
├── searcher.py
├── crossref_searcher.py
├── openalex_searcher.py
├── pubmed_searcher.py
├── semantic_scholar_searcher.py
├── scopus_searcher.py
├── downloader.py
├── monitor.py
├── classifier.py
└── insight.py
```
