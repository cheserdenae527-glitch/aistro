# backend/tests/test_scoring_config.py
from app.services.scoring_config import load_scoring_config


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


def test_fallback_on_load_error(monkeypatch):
    def boom():
        raise RuntimeError("config broken")

    monkeypatch.setattr("crawler.config.load_config", boom)
    cfg = load_scoring_config()
    assert cfg["gate"]["stale_days"] == 60            # pristine defaults
