"""Tests for CJK/EN script fairness in quality tier assignment."""

from agent_wiki import quality


def test_tier_script_fairness_basic_level():
    """Equivalent basic-tier content in CJK and Latin should tier equally."""
    # Basic tier: prose_weight >= 200 and prose_weight > 0

    # CJK: 20 chars × 10 = 200 weight
    body_cjk = "这是一个基本的测试内容用于验证基本层级的判定。"  # 20 CJK chars

    # Latin: 13 words × 16 = 208 weight (≈ same)
    body_latin = "This is a basic test content to verify basic tier assignment with words."  # 13 words

    tier_cjk = quality.compute_tier(body_cjk)
    tier_latin = quality.compute_tier(body_latin)

    assert tier_cjk == "basic"
    assert tier_latin == "basic"


def test_tier_script_fairness_standard_level():
    """Equivalent standard-tier content in CJK and Latin should tier equally."""
    # Standard tier: sections >= 2 AND effective_prose >= 600

    # CJK: 2 sections + exactly 60 chars × 10 = 600 weight
    cjk_prose = "标" * 60  # Exactly 60 identical CJK chars
    body_cjk = f"## 第一节\n\n{cjk_prose[:30]}\n\n## 第二节\n\n{cjk_prose[30:]}"

    # Latin: 2 sections + exactly 38 words × 16 = 608 weight
    body_latin = f"## First Section\n\n{' '.join(['word']*19)}\n\n## Second Section\n\n{' '.join(['word']*19)}"

    tier_cjk = quality.compute_tier(body_cjk)
    tier_latin = quality.compute_tier(body_latin)

    assert tier_cjk == "standard"
    assert tier_latin == "standard"


def test_tier_script_fairness_rich_level():
    """Equivalent rich-tier content in CJK and Latin should tier equally."""
    # Rich tier: sections >= 4 AND effective_prose >= 1500 AND (evidence_lines >= 1 OR has_image)

    # CJK: 4 sections + exactly 150 chars × 10 = 1500 weight + 1 evidence
    cjk_prose = "测" * 150
    body_cjk = f"""## 引言

{cjk_prose[:40]}

## 方法

> 证据

{cjk_prose[40:80]}

## 结果

{cjk_prose[80:120]}

## 讨论

{cjk_prose[120:]}"""

    # Latin: 4 sections + exactly 94 words × 16 = 1504 weight + 1 evidence
    body_latin = f"""## Introduction

{' '.join(['word']*24)}

## Methods

> Evidence

{' '.join(['word']*23)}

## Results

{' '.join(['word']*24)}

## Discussion

{' '.join(['word']*23)}"""

    tier_cjk = quality.compute_tier(body_cjk)
    tier_latin = quality.compute_tier(body_latin)

    assert tier_cjk == "rich"
    assert tier_latin == "rich"


def test_tier_script_fairness_premium_level():
    """Equivalent premium-tier content in CJK and Latin should tier equally."""
    # Premium tier: sections >= 6 AND effective_prose >= 3000 AND evidence_lines >= 3

    # CJK: 6 sections + exactly 300 chars × 10 = 3000 weight + 3 evidence
    cjk_prose = "研" * 300
    body_cjk = f"""## 背景

{cjk_prose[:50]}

## 文献综述

> 证据一
> 证据二
> 证据三

{cjk_prose[50:100]}

## 研究方法

{cjk_prose[100:150]}

## 数据分析

{cjk_prose[150:200]}

## 结果与发现

{cjk_prose[200:250]}

## 结论与展望

{cjk_prose[250:]}"""

    # Latin: 6 sections + exactly 188 words × 16 = 3008 weight + 3 evidence
    body_latin = f"""## Background

{' '.join(['word']*32)}

## Literature Review

> Evidence one
> Evidence two
> Evidence three

{' '.join(['word']*31)}

## Research Methods

{' '.join(['word']*31)}

## Data Analysis

{' '.join(['word']*31)}

## Results and Findings

{' '.join(['word']*31)}

## Conclusion and Outlook

{' '.join(['word']*32)}"""

    tier_cjk = quality.compute_tier(body_cjk)
    tier_latin = quality.compute_tier(body_latin)

    assert tier_cjk == "premium"
    assert tier_latin == "premium"


def test_tier_script_fairness_mixed_content():
    """Mixed CJK/Latin content uses combined weight."""
    # Mixed: enough content to reach 600+ weight + 2 sections = standard
    body_mixed = """## Introduction 介绍

这是一个混合语言的测试内容包含中文字符和英文单词需要足够的内容量。

## Methods 方法

This section contains English words and Chinese characters 以及更多的中文内容来达到标准层级的门槛要求这里还需要补充一些文字。"""

    tier_mixed = quality.compute_tier(body_mixed)

    # Should reach standard tier (sections >= 2, effective_prose >= 600)
    assert tier_mixed == "standard"


def test_tier_threshold_boundaries_cjk_vs_latin():
    """Verify threshold boundaries work equally for both scripts."""
    # Test at exactly 200 weight boundary (basic tier minimum with prose_weight > 0)

    # CJK: exactly 20 chars = 200 weight
    body_cjk_200 = "测" * 20  # Exactly 20 CJK chars

    # Latin: exactly 13 words = 208 weight
    body_latin_200 = " ".join(["word"] * 13)  # Exactly 13 words

    tier_cjk = quality.compute_tier(body_cjk_200)
    tier_latin = quality.compute_tier(body_latin_200)

    assert tier_cjk == "basic"
    assert tier_latin == "basic"
