from app.services.blogger_comments import analyze_comments


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
