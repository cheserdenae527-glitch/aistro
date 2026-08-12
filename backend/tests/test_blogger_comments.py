from app.services.blogger_comments import analyze_comments, collect_comments


def _mk_note(i: int, published_at: str, **stats) -> dict:
    base = {"liked": 100, "collected": 10, "comments": 5, "shared": 2}
    base.update(stats)
    return {
        "platform_note_id": f"note{i}",
        "xsec_token": f"token{i}",
        "stats": base,
        "published_at": published_at,
    }


class _FakeResult:
    def __init__(self, success=True, data=None):
        self.success = success
        self.data = data or []
        self.error = None


class _FakeCrawler:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def get_comments(self, url):
        self.calls.append(url)
        return self.results.pop(0)


def test_analyze_comments_intent_spam_negative():
    comments = [
        {"content": "这家店在哪呀 人均多少"},
        {"content": "好吃吗 想周末去试试"},
        {"content": "太棒了 学习了 支持"},
        {"content": "广告吧 取关了"},
        {"content": "求地址 求菜单"},
    ]
    res = analyze_comments(comments)
    assert res["intent_ratio"] >= 0.4
    assert res["spam_ratio"] >= 0.1
    assert res["negative_ratio"] >= 0.1


def test_analyze_comments_empty():
    res = analyze_comments([])
    assert res["intent_ratio"] == 0.0
    assert res["spam_ratio"] == 0.0
    assert res["negative_ratio"] == 0.0


def test_analyze_comments_ignores_empty_content():
    res = analyze_comments([{"content": ""}, {"content": None}, {"content": "求地址"}])
    assert res["sample"] == 1
    assert res["intent_ratio"] == 1.0


def test_collect_comments_selection_respects_note_limit_and_newest():
    import asyncio

    notes = [
        _mk_note(1, "2026-08-01T12:00:00+08:00", liked=500, collected=100, comments=50, shared=20),
        _mk_note(2, "2026-08-02T12:00:00+08:00", liked=400, collected=80, comments=40, shared=15),
        _mk_note(3, "2026-08-03T12:00:00+08:00", liked=300, collected=60, comments=30, shared=10),
        _mk_note(4, "2026-08-04T12:00:00+08:00", liked=10, collected=1, comments=0, shared=0),
    ]
    crawler = _FakeCrawler([
        _FakeResult(data=[{"content": "好吃吗"}]),
        _FakeResult(data=[{"content": "太棒了"}]),
    ])
    res = asyncio.run(collect_comments(crawler, notes, note_limit=2, per_note=5))
    assert res is not None
    assert res["sample"] == 2
    assert len(crawler.calls) == 2  # note_limit 生效
    assert "explore/note4" in crawler.calls[0]  # 最新一篇被前置补入


def test_collect_comments_all_fail_returns_none():
    import asyncio

    notes = [_mk_note(i, f"2026-08-0{i}T12:00:00+08:00") for i in range(1, 4)]
    crawler = _FakeCrawler([_FakeResult(success=False), _FakeResult(success=False)])
    res = asyncio.run(collect_comments(crawler, notes, note_limit=2, per_note=5))
    assert res is None
    assert len(crawler.calls) == 2


def test_collect_comments_empty_data_returns_none():
    import asyncio

    notes = [_mk_note(1, "2026-08-01T12:00:00+08:00"), _mk_note(2, "2026-08-02T12:00:00+08:00")]
    crawler = _FakeCrawler([_FakeResult(data=[]), _FakeResult(data=[])])
    res = asyncio.run(collect_comments(crawler, notes, note_limit=2, per_note=5))
    assert res is None


def test_collect_comments_exception_returns_none():
    import asyncio

    notes = [_mk_note(1, "2026-08-01T12:00:00+08:00"), _mk_note(2, "2026-08-02T12:00:00+08:00")]

    class _BoomCrawler:
        def get_comments(self, url):
            raise RuntimeError("boom")

    res = asyncio.run(collect_comments(_BoomCrawler(), notes, note_limit=2, per_note=5))
    assert res is None


def test_collect_comments_mixed_returns_analysis():
    import asyncio

    notes = [_mk_note(1, "2026-08-01T12:00:00+08:00"), _mk_note(2, "2026-08-02T12:00:00+08:00")]
    comments = [{"content": "这家店在哪呀"}, {"content": "太棒了 支持"}]
    crawler = _FakeCrawler([
        _FakeResult(success=False),  # 第一篇抓取失败
        _FakeResult(data=comments),  # 第二篇成功
    ])
    res = asyncio.run(collect_comments(crawler, notes, note_limit=2, per_note=5))
    assert res == analyze_comments(comments)
    assert res["sample"] == 2
