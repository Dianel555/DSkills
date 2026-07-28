"""
论文自动归类模块
基于关键词、期刊、学科映射自动为论文分类
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from . import SKILL_DATA_DIR


# ============================================================
# 分类配置（可扩展）
# ============================================================

CATEGORIES = {
    "ionogel": {
        "label": "离子凝胶",
        "keywords": [
            "ionogel", "ionic liquid gel", "ion gel", "gel polymer electrolyte",
            "ion-conducting gel", "ionic gel polymer", "deep eutectic gel",
            "DES gel", "ionic liquid polymer", "ionogel electrolyte",
            "ionogel membrane", "ionogel separator"
        ],
        "journals": [
            "journal of power sources", "electrochimica acta", "solid state ionics",
            "journal of materials chemistry a", "acs applied materials & interfaces",
            "journal of the electrochemical society"
        ]
    },
    "electrolyte": {
        "label": "电解质",
        "keywords": [
            "electrolyte", "polymer electrolyte", "solid electrolyte",
            "liquid electrolyte", "gel electrolyte", "ionic conductivity",
            "electrochemical stability", "transference number",
            "lithium ion conductor", "sodium ion conductor"
        ],
        "journals": [
            "journal of power sources", "electrochimica acta", "solid state ionics",
            "advanced energy materials", "energy storage materials"
        ]
    },
    "battery": {
        "label": "电池",
        "keywords": [
            "battery", "lithium battery", "sodium battery", "zinc battery",
            "energy storage", "supercapacitor", "secondary battery",
            "rechargeable battery", "battery performance", "cycle life"
        ],
        "journals": [
            "journal of power sources", "electrochimica acta",
            "advanced energy materials", "nano energy", "acs nano"
        ]
    },
    "sensor": {
        "label": "传感器",
        "keywords": [
            "sensor", "biosensor", "gas sensor", " electrochemical sensor",
            "ionic liquid sensor", "ionogel sensor", "chemi-resistor",
            "sensing performance", "selectivity", "detection limit"
        ],
        "journals": [
            "sensors and actuators", "analytical chemistry", "acs sensors",
            "biosensors & bioelectronics", "analyst"
        ]
    },
    "actuator": {
        "label": "执行器",
        "keywords": [
            "actuator", "artificial muscle", "electroactive polymer",
            "soft actuator", "ionic actuator", "bending actuator",
            "gripper", "soft robotics", "shape memory"
        ],
        "journals": [
            "advanced materials", "soft matter", "acs applied materials & interfaces",
            "advanced functional materials", "macromolecules"
        ]
    },
    "separation": {
        "label": "分离膜",
        "keywords": [
            "membrane", "separation", "permeation", "pervaporation",
            "gas separation", "nanofiltration", "reverse osmosis",
            "ion selective membrane", "proton exchange membrane",
            "anion exchange membrane", "ionogel membrane"
        ],
        "journals": [
            "journal of membrane science", "separation and purification technology",
            "acs applied materials & interfaces", "polymer"
        ]
    },
    "theoretical": {
        "label": "理论研究",
        "keywords": [
            "molecular dynamics", "dft", "density functional theory",
            "simulation", "first principles", "monte carlo",
            "coarse-grained", "phase field", "machine learning",
            "deep learning", "neural network", "property prediction"
        ],
        "journals": [
            "journal of chemical theory and computation", "acs journal of chemical theory",
            "physical review letters", "jphyschem letters", "jphyschem c"
        ]
    },
    "review": {
        "label": "综述",
        "keywords": [
            "review", "perspective", "minireview", "tutorial review",
            "advances in", "recent progress", "state of the art",
            "overview", "prospect", "outlook"
        ],
        "journals": []
    }
}

# 优先级权重
WEIGHTS = {
    "keyword_match": 3.0,
    "journal_match": 2.0,
    "category_boost": 1.5
}


# ============================================================
# 核心分类器
# ============================================================

class PaperClassifier:
    """论文自动分类器。"""

    def __init__(self, custom_categories: Optional[Dict[str, Any]] = None):
        self.categories = {**CATEGORIES}
        if custom_categories:
            self.categories.update(custom_categories)
        self._compile_patterns()

    def _compile_patterns(self):
        """预编译所有关键词正则"""
        self._compiled: Dict[str, Dict[str, List[re.Pattern]]] = {}
        for cat_name, cat_config in self.categories.items():
            kw_patterns = [re.compile(r'\b' + re.escape(kw) + r'\b', re.IGNORECASE)
                          for kw in cat_config.get("keywords", [])]
            j_patterns = [re.compile(r'\b' + re.escape(j) + r'\b', re.IGNORECASE)
                         for j in cat_config.get("journals", [])]
            self._compiled[cat_name] = {
                "keywords": kw_patterns,
                "journals": j_patterns
            }

    def classify(self, paper: Any) -> Dict[str, Any]:
        """
        对单篇论文分类
        返回: {
            "categories": [{"name": str, "score": float, "label": str}],
            "primary": str,  # 最高分类名
            "confidence": float
        }
        """
        title = _paper_value(paper, 'title') or ''
        abstract = _paper_value(paper, 'abstract') or ''
        journal = _paper_value(paper, 'journal') or ''
        text = f"{title} {abstract}"

        scores: Dict[str, float] = {name: 0.0 for name in self.categories}

        for cat_name, patterns in self._compiled.items():
            kw_matches = sum(1 for p in patterns["keywords"] if p.search(text))
            j_matches = sum(1 for p in patterns["journals"] if p.search(journal))

            scores[cat_name] = (
                kw_matches * WEIGHTS["keyword_match"] +
                j_matches * WEIGHTS["journal_match"]
            )

        # 归一化
        max_score = max(scores.values()) if scores else 0.0
        if max_score > 0:
            scores = {k: v / max_score for k, v in scores.items()}

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        # 取前3个
        categories = []
        for cat_name, score in ranked[:3]:
            if score > 0.1:
                categories.append({
                    "name": cat_name,
                    "score": round(score, 3),
                    "label": self.categories[cat_name].get("label", cat_name)
                })

        primary = categories[0]["name"] if categories else "uncategorized"
        confidence = categories[0]["score"] if categories else 0.0

        return {
            "categories": categories,
            "primary": primary,
            "confidence": round(confidence, 3)
        }

    def batch_classify(self, papers: List[Any]) -> List[Dict[str, Any]]:
        """批量分类"""
        results = []
        for paper in papers:
            result = self.classify(paper)
            result["paper"] = {
                "title": _paper_value(paper, 'title') or '',
                "doi": _paper_value(paper, 'doi') or '',
                "year": _paper_value(paper, 'year') or 0,
            }
            results.append(result)
        return results

    def get_distribution(self, results: List[Dict[str, Any]]) -> Dict[str, int]:
        """获取分类分布统计"""
        dist: Dict[str, int] = {}
        for r in results:
            primary = r.get("primary", "uncategorized")
            dist[primary] = dist.get(primary, 0) + 1
        return dist

    def add_category(self, name: str, keywords: List[str],
                     journals: Optional[List[str]] = None, label: str = ""):
        """动态添加分类"""
        self.categories[name] = {
            "keywords": keywords,
            "journals": journals or [],
            "label": label or name
        }
        self._compile_patterns()


# ============================================================
# 文件IO
# ============================================================

def save_classification_report(results: List[Dict[str, Any]],
                               report_path: Optional[str] = None) -> str:
    """保存分类报告"""
    if report_path is None:
        report_path = str(SKILL_DATA_DIR / "classification_report.json")

    SKILL_DATA_DIR.mkdir(parents=True, exist_ok=True)

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    return report_path


def load_classification_report(report_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """加载历史分类报告"""
    if report_path is None:
        report_path = str(SKILL_DATA_DIR / "classification_report.json")

    if not Path(report_path).exists():
        return []

    with open(report_path, "r", encoding="utf-8") as f:
        return json.load(f)


def format_report_markdown(results: List[Dict[str, Any]]) -> str:
    """生成Markdown格式的分类报告"""
    if not results:
        return "# 论文分类报告\n\n暂无数据"

    # 统计
    dist = PaperClassifier().get_distribution(results)
    total = len(results)

    lines = [
        "# 论文自动分类报告",
        f"",
        f"> 生成时间: {datetime.now().isoformat()}",
        f"> 总论文数: {total}",
        "",
        "## 分类分布",
        "",
        "| 分类 | 数量 | 占比 |",
        "|------|------|------|"
    ]

    for cat, count in sorted(dist.items(), key=lambda x: x[1], reverse=True):
        pct = f"{count/total*100:.1f}%"
        lines.append(f"| {cat} | {count} | {pct} |")

    lines.extend([
        "",
        "## 分类详情",
        ""
    ])

    # 按分类分组
    from collections import defaultdict
    groups = defaultdict(list)
    for r in results:
        groups[r.get("primary", "uncategorized")].append(r)

    for cat_name, papers in sorted(groups.items(), key=lambda x: len(x[1]), reverse=True):
        label = CATEGORIES.get(cat_name, {}).get("label", cat_name)
        lines.append(f"### {label} ({len(papers)}篇)")
        lines.append("")

        for p in papers[:10]:
            title = p.get("paper", {}).get("title", "Unknown")
            doi = p.get("paper", {}).get("doi", "")
            conf = p.get("confidence", 0)
            sub_cats = [c["label"] for c in p.get("categories", [])[1:]]
            cat_str = ", ".join(sub_cats) if sub_cats else "-"

            lines.append(f"- **{title}**")
            if doi:
                lines.append(f"  - DOI: {doi}")
            lines.append(f"  - 置信度: {conf:.2f}")
            if cat_str != "-":
                lines.append(f"  - 子分类: {cat_str}")
            lines.append("")

    return "\n".join(lines)


def _paper_value(paper: Any, key: str) -> Any:
    if isinstance(paper, Mapping):
        return paper.get(key)
    return getattr(paper, key, None)
