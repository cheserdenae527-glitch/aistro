# backend/tests/test_scoring_config.py
import pytest

from app.services.scoring_config import clear_scoring_config_cache, load_scoring_config


@pytest.fixture(autouse=True)
def _no_config_cache():
    # load_scoring_config 进程级缓存：每个用例前后清空，保证 monkeypatch 生效与用例隔离
    clear_scoring_config_cache()
    yield
    clear_scoring_config_cache()


def test_defaults_present():
    cfg = load_scoring_config()
    assert set(cfg["weights"]) == {
        "seeding_depth", "verticality", "stable_output", "sustained_operation", "growth_trend",
        "cost_effectiveness",
    }
    assert abs(sum(cfg["weights"].values()) - 1.0) < 1e-9
    assert "T1" in cfg["tiers"] and "T4" in cfg["tiers"]
    assert cfg["tiers"]["T1"]["growth_baseline"] > 0
    # 分层唯一事实来源：points/min_healthy 为加权互动率百分数口径，min_healthy_rate 为收藏率百分数口径
    assert cfg["tiers"]["T1"]["min_healthy"] == 6.906
    assert cfg["tiers"]["T1"]["min_healthy_rate"] == 1.0
    assert len(cfg["tiers"]["T2"]["points"]) == 4
    assert cfg["tiers"]["T4"]["max"] is None
    assert "探店" in cfg["verticality"]["food_keywords"]
    assert "gate" in cfg and cfg["gate"]["stale_days"] == 60


def test_json_override(monkeypatch):
    from crawler.config import load_config  # noqa: F401  (target module for patching)

    def fake_load_config():
        return {
            "blogger_scoring": {
                "gate": {"stale_days": 30},          # dict override deep-merges
                "weights": {"seeding_depth": 0.4},   # non-dict leaf replaced
            }
        }

    monkeypatch.setattr("crawler.config.load_config", fake_load_config)
    cfg = load_scoring_config()
    # override value wins
    assert cfg["gate"]["stale_days"] == 30
    # sibling keys survive deep-merge
    assert cfg["gate"]["fake_ratio"] == 0.20
    assert cfg["weights"]["verticality"] == 0.20
    # non-dict value replaced wholesale
    assert cfg["weights"]["seeding_depth"] == 0.4
    # untouched branches keep defaults
    assert cfg["verticality"]["food_keywords"][0] == "探店"
    # tiers 默认仍完整（含 points/min_healthy）
    assert cfg["tiers"]["T2"]["min_healthy"] == 2.946


def test_fallback_on_load_error(monkeypatch):
    def boom():
        raise RuntimeError("config broken")

    monkeypatch.setattr("crawler.config.load_config", boom)
    cfg = load_scoring_config()
    assert cfg["gate"]["stale_days"] == 60            # pristine defaults


def test_config_cached_and_deep_copied():
    a = load_scoring_config()
    a["gate"]["stale_days"] = 999                     # 篡改返回值
    b = load_scoring_config()
    assert a is not b
    assert b["gate"]["stale_days"] == 60              # 缓存未被污染
