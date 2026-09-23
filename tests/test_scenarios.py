import pandas as pd

from futures_analyzer.scenarios.builder import build_scenarios
from futures_analyzer.scenarios.scoring import WEIGHTS, score_snapshot


def tf(ema_trend=None, trend_by_breaks=None, above_vwap=None, bullish_break=None):
    return {
        "technical": {"ema_trend": ema_trend or "unknown", "above_vwap": above_vwap},
        "structure": {"trend_by_breaks": trend_by_breaks, "bullish_break_level": bullish_break, "bearish_break_level": None},
    }


def zone(low, high, sources=("X",)):
    return {"low": low, "high": high, "sources": list(sources), "strength": len(sources)}


def base_snapshot(direction="bullish"):
    return {
        "instrument": "NQ",
        "data_source": "yfinance (10-15 dk gecikmeli)",
        "timeframes": {
            "1d": tf(ema_trend=direction),
            "4h": tf(ema_trend=direction, trend_by_breaks=direction),
            "1h": tf(ema_trend=direction, trend_by_breaks=direction),
            "15m": tf(trend_by_breaks=direction, above_vwap=direction == "bullish"),
            "5m": None,
        },
        "levels": {
            "zone_tolerance": 5.0,  # ATR 20 -> yarım ATR = 10
            "at_price": [],
            "resistance": [zone(105, 106), zone(108, 108), zone(120, 121), zone(140, 140)],
            "support": [zone(95, 96), zone(80, 81), zone(70, 70)],
        },
        "liquidity": None,
        "macro": None,
        "intermarket": None,
        "news": {"calendar": {"event_risk": None, "just_released": []}, "headlines": []},
    }


def test_weights_sum_to_100():
    assert sum(WEIGHTS.values()) == 100


def test_fully_bullish_technical_picture():
    score = score_snapshot(base_snapshot("bullish"))

    # trend 20 + structure 20 + vwap 10 = 50; diğerleri veri yok -> 0
    assert score["total"] == 50.0
    assert score["bias"] == "bullish"
    assert score["components"]["trend"]["points"] == 20.0
    assert score["components"]["macro"]["available"] is False
    assert score["coverage"] == 20 + 20 + 10 + 5  # news bölümü var ama yönlü başlık yok


def test_fully_bearish_is_mirror():
    assert score_snapshot(base_snapshot("bearish"))["total"] == -50.0


def test_mixed_signals_are_neutral():
    snapshot = base_snapshot("bullish")
    snapshot["timeframes"]["4h"] = tf(ema_trend="bearish", trend_by_breaks="bearish")
    snapshot["timeframes"]["1h"] = tf(ema_trend="bearish", trend_by_breaks="bearish")
    snapshot["timeframes"]["15m"] = tf(trend_by_breaks="bearish", above_vwap=True)

    score = score_snapshot(snapshot)

    # trend: 0.4 - 0.35 - 0.25 = -0.2 -> -4 ; structure: -1 -> -20 ; vwap +10
    assert score["total"] == -14.0
    assert score["bias"] == "neutral"


def test_macro_and_intermarket_components():
    snapshot = base_snapshot("bullish")
    snapshot["macro"] = {"us10y": {"change_20d": -0.25}}  # 25 bp düşüş -> +1
    snapshot["intermarket"] = {
        "assets": {
            "ES": {"relationship": 1, "direction": "up"},
            "DXY": {"relationship": -1, "direction": "down"},
            "VIX": {"relationship": -1, "direction": "flat"},
            "YM": None,
        },
        "smt": {"partner": "ES", "divergence": "bearish"},
    }

    components = score_snapshot(snapshot)["components"]

    assert components["macro"]["value"] == 1.0
    # (1 + 1 + 0) / 3 = 0.67, bearish SMT -0.5 -> 0.17
    assert components["intermarket"]["value"] == 0.17


def test_volume_component():
    index = pd.date_range("2026-06-15 10:00", periods=7, freq="1h", tz="UTC")
    hourly = pd.DataFrame({
        "open": [100, 100, 100, 100, 100, 100, 100],
        # Tarihler geçmişte, hepsi kapanmış; son 5 mum (index 2-6): -, +, +, +, +
        "close": [101, 101, 99, 101, 101, 101, 101],
        "high": 102, "low": 98,
        "volume": [10, 10, 30, 10, 10, 10, 10],
    }, index=index)

    component = score_snapshot(base_snapshot(), hourly)["components"]["volume"]

    assert component["value"] == round((10 - 30 + 10 + 10 + 10) / 70, 2)


def test_scenarios_use_only_snapshot_levels():
    snapshot = base_snapshot("bullish")
    scenarios = build_scenarios(snapshot, score_snapshot(snapshot))

    bull, bear = scenarios["bullish"], scenarios["bearish"]
    assert scenarios["primary"] == "bullish"
    assert bull["trigger_level"] == 106        # en yakın direnç zone'unun üstü
    assert bull["invalidation_level"] == 95    # en yakın destek zone'unun altı
    # 108 tetiğe (106) çok yakın (< 10) -> atlanır; 120 ve 140 hedef olur
    assert [t["level"] for t in bull["targets"]] == [120, 140]
    assert bear["trigger_level"] == 95
    assert [t["level"] for t in bear["targets"]] == [81, 70]
    assert scenarios["neutral"]["range"] == [95, 106]


def test_price_inside_a_zone_is_the_trigger_for_both_sides():
    snapshot = base_snapshot()
    snapshot["levels"]["at_price"] = [zone(99, 101)]

    scenarios = build_scenarios(snapshot, score_snapshot(snapshot))

    assert scenarios["bullish"]["trigger_level"] == 101
    assert scenarios["bearish"]["trigger_level"] == 99
    assert [t["level"] for t in scenarios["bullish"]["targets"]] == [120, 140]  # 105 tetiğe çok yakın


def test_risk_factors_include_event_risk_and_opposing_components():
    snapshot = base_snapshot("bullish")
    snapshot["news"]["calendar"]["event_risk"] = {"title": "CPI m/m", "minutes_until": 35, "imminent": True}

    scenarios = build_scenarios(snapshot, score_snapshot(snapshot))

    assert "YAKIN OLAY RİSKİ: CPI m/m (35 dk sonra)" in scenarios["neutral"]["risk_factors"]
    assert any(r.startswith("trend:") for r in scenarios["bearish"]["risk_factors"])  # bullish trend bearish senaryoya risk
    assert not any(r.startswith("trend:") for r in scenarios["bullish"]["risk_factors"])


def test_no_levels_no_scenarios():
    snapshot = base_snapshot()
    snapshot["levels"] = None

    assert build_scenarios(snapshot, score_snapshot(snapshot)) is None
