import math
import urllib.error
import urllib.request

import pytest

from literature_searcher import semantic_scholar_searcher as semantic


@pytest.mark.parametrize("header", ["999999999", "NaN", "inf", "-50", "Wed, 01 Jan 2099 00:00:00 GMT"])
def test_retry_after_delay_is_finite_and_bounded(monkeypatch, header):
    sleeps, calls = [], []
    def fail(req, timeout):
        calls.append(1)
        raise urllib.error.HTTPError(req.full_url, 429, "limited", {"Retry-After": header}, None)
    monkeypatch.setattr(semantic.urllib.request, "urlopen", fail)
    monkeypatch.setattr(semantic.time, "sleep", sleeps.append)
    request = urllib.request.Request("https://example.invalid")
    assert semantic.SemanticScholarSearcher._request_with_retry(request, max_attempts=3) is None
    assert len(calls) == 3 and len(sleeps) == 2
    assert all(math.isfinite(s) and 0 <= s <= 30 for s in sleeps)
