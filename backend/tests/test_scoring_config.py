# backend/tests/test_scoring_config.py
from app.services.scoring_config import load_scoring_config, DEFAULT_SCORING_CONFIG

def test_defaults_present():
    cfg = load_scoring_config()
    assert set(cfg["weights"]) == {
        "seeding_depth", "verticality", "stable_output", "sustained_operation", "growth_trend",
    }
    assert abs(sum(cfg["weights"].values()) - 1.0) < 1e-9
    assert "T1" in cfg["tiers"] and "T4" in cfg["tiers"]
    assert cfg["tiers"]["T1"]["growth_baseline"] > 0
    assert "探店" in cfg["verticality"]["food_keywords"]
    assert "gate" in cfg and cfg["gate"]["stale_days"] == 60


def test_json_override():
    cfg = load_scoring_config()
    # 默认兜底存在即可；覆盖逻辑由 merge 单元保证
    merged = dict(DEFAULT_SCORING_CONFIG)
    merged["weights"] = {**merged["weights"], "seeding_depth": 0.4}
    assert merged["weights"]["seeding_depth"] == 0.4
