"""Bir analizin sonradan ne olduğunu ölçer (5 dakikalık mumlarla).

- forward_returns: analizden 1 saat, 4 saat ve 1 gün sonra fiyat % kaç değişti
- direction_correct: bias yönü 4 saatlik değişimle aynı mı (nötr bias için None)
- scenario_outcome: 1 gün içinde hangi senaryo tetiklendi, hedefe mi invalidation'a mı önce ulaştı

Kurallar (senaryo metinleriyle aynı):
- Tetik: 5M kapanışın tetik seviyesinin ötesinde olması
- Hedef: ilk hedefe iğneyle bile dokunulması
- Invalidation: 5M kapanışın invalidation seviyesinin ötesinde olması
Aynı mumda hem hedef hem invalidation olursa sonuç "ambiguous" (hangisinin önce olduğu bilinemez).
"""

import pandas as pd

HORIZONS = {"1h": pd.Timedelta(hours=1), "4h": pd.Timedelta(hours=4), "1d": pd.Timedelta(days=1)}
SCENARIO_WINDOW = pd.Timedelta(days=1)


def forward_returns(five_min: pd.DataFrame, as_of: pd.Timestamp, price: float) -> dict:
    """Her ufuk için yüzde değişim. Ufuk henüz gelmediyse (veri yoksa) None."""
    result = {}
    for name, delta in HORIZONS.items():
        target = as_of + delta
        if five_min.empty or five_min.index[-1] < target - pd.Timedelta(minutes=5):
            result[name] = None
            continue
        before = five_min[five_min.index < target]
        later_price = float(before["close"].iloc[-1])
        result[name] = round((later_price / price - 1) * 100, 3)
    return result


def direction_correct(bias: str, returns: dict) -> bool | None:
    change = returns.get("4h")
    if bias == "neutral" or change is None or change == 0:
        return None
    return (change > 0) == (bias == "bullish")


def scenario_outcome(five_min: pd.DataFrame, as_of: pd.Timestamp, scenarios: dict | None) -> dict:
    if not scenarios:
        return {"result": "no_scenarios"}
    window = five_min[(five_min.index >= as_of) & (five_min.index < as_of + SCENARIO_WINDOW)]
    if five_min.empty or five_min.index[-1] < as_of + SCENARIO_WINDOW - pd.Timedelta(minutes=5):
        return {"result": "pending"}

    bull, bear = scenarios["bullish"], scenarios["bearish"]
    for position, (ts, bar) in enumerate(window.iterrows()):
        up = bar["close"] > bull["trigger_level"]
        down = bar["close"] < bear["trigger_level"]
        if up or down:
            side, scenario = ("bullish", bull) if up else ("bearish", bear)
            result = _after_trigger(window.iloc[position + 1:], side, scenario)
            return {"triggered": side, "trigger_ts": ts.isoformat(), **result}
    return {"result": "no_trigger"}


def _after_trigger(bars: pd.DataFrame, side: str, scenario: dict) -> dict:
    if not scenario["targets"]:
        return {"result": f"{side}_no_target"}
    target = scenario["targets"][0]["level"]
    invalidation = scenario["invalidation_level"]

    for ts, bar in bars.iterrows():
        if side == "bullish":
            hit, invalid = bar["high"] >= target, bar["close"] < invalidation
        else:
            hit, invalid = bar["low"] <= target, bar["close"] > invalidation
        if hit and invalid:
            return {"result": "ambiguous", "resolved_ts": ts.isoformat()}
        if hit:
            return {"result": f"{side}_target", "resolved_ts": ts.isoformat()}
        if invalid:
            return {"result": f"{side}_invalidated", "resolved_ts": ts.isoformat()}
    return {"result": f"{side}_open"}


def evaluate(five_min: pd.DataFrame, as_of: pd.Timestamp, price: float, bias: str, scenarios: dict | None) -> dict:
    returns = forward_returns(five_min, as_of, price)
    return {
        "returns": returns,
        "direction_correct": direction_correct(bias, returns),
        "scenario": scenario_outcome(five_min, as_of, scenarios),
        "complete": returns["1d"] is not None,
    }
