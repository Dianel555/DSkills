"""Tests for script-aware prose_weight metric."""

from agent_wiki import quality


def test_prose_weight_counts_cjk_characters():
    """CJK ideographs (EAW W/F + category L/N) are counted."""
    body = "这是一个测试。"  # 6 CJK chars + 1 punctuation
    metrics = quality.compute_metrics(body)

    # Expected: 6 CJK chars × 10 = 60
    assert "prose_weight" in metrics
    assert metrics["prose_weight"] >= 60
    assert metrics["cjk_chars"] == 6


def test_prose_weight_counts_latin_words():
    """Latin word runs are counted."""
    body = "This is a test sentence."  # 5 words
    metrics = quality.compute_metrics(body)

    # Expected: 5 words × 16 = 80
    assert "prose_weight" in metrics
    assert metrics["prose_weight"] >= 80
    assert metrics["latin_words"] == 5


def test_prose_weight_mixed_cjk_latin():
    """Mixed CJK and Latin content is weighted correctly."""
    body = "Python 是一种编程语言。"  # 1 word + 7 CJK chars
    metrics = quality.compute_metrics(body)

    # Expected: 7 × 10 + 1 × 16 = 86
    expected = 7 * 10 + 1 * 16
    assert metrics["prose_weight"] == expected
    assert metrics["cjk_chars"] == 7
    assert metrics["latin_words"] == 1


def test_prose_weight_excludes_cjk_punctuation():
    """Wide/fullwidth punctuation should not count as CJK chars."""
    body = "测试。、，「」"  # 2 CJK chars + 5 punctuation marks
    metrics = quality.compute_metrics(body)

    # Only count actual CJK characters, not punctuation
    assert metrics["cjk_chars"] == 2
    assert metrics["prose_weight"] == 2 * 10


def test_prose_weight_handles_halfwidth_katakana():
    """Halfwidth katakana (EAW=H) should be normalized to fullwidth."""
    # ｱｲｳ (halfwidth) should be treated same as アイウ (fullwidth)
    body_halfwidth = "ｱｲｳ"
    body_fullwidth = "アイウ"

    metrics_half = quality.compute_metrics(body_halfwidth)
    metrics_full = quality.compute_metrics(body_fullwidth)

    # Both should count as 3 CJK chars
    assert metrics_half["cjk_chars"] == metrics_full["cjk_chars"]
    assert metrics_half["prose_weight"] == metrics_full["prose_weight"]


def test_prose_weight_separates_at_wide_chars():
    """Wide chars should act as word separators for Latin."""
    body = "foo。bar"  # 2 words separated by fullwidth period
    metrics = quality.compute_metrics(body)

    assert metrics["latin_words"] == 2  # foo and bar as separate words


def test_prose_weight_applies_nfc_normalization():
    """All text should be NFC-normalized before counting."""
    # NFD: decomposed form (e + combining acute)
    body_nfd = "café"  # 4 base + 1 combining
    # NFC: composed form
    body_nfc = "café"  # 4 chars

    metrics_nfd = quality.compute_metrics(body_nfd)
    metrics_nfc = quality.compute_metrics(body_nfc)

    # Should produce same counts after normalization
    assert metrics_nfd["prose_weight"] == metrics_nfc["prose_weight"]


def test_prose_weight_deterministic():
    """Same input produces same prose_weight."""
    body = "测试 test 123"

    metrics1 = quality.compute_metrics(body)
    metrics2 = quality.compute_metrics(body)

    assert metrics1["prose_weight"] == metrics2["prose_weight"]
    assert metrics1["cjk_chars"] == metrics2["cjk_chars"]
    assert metrics1["latin_words"] == metrics2["latin_words"]


def test_prose_chars_retained_for_transparency():
    """prose_chars should still be computed alongside prose_weight."""
    body = "测试内容"
    metrics = quality.compute_metrics(body)

    assert "prose_chars" in metrics
    assert "prose_weight" in metrics
    assert metrics["prose_chars"] == 4  # Original char count


def test_prose_weight_formula_10_16_ratio():
    """Verify the 10×CJK + 16×Latin formula."""
    body = "三个字 three words here"  # 3 CJK + 3 Latin words
    metrics = quality.compute_metrics(body)

    expected = 3 * 10 + 3 * 16
    assert metrics["prose_weight"] == expected
