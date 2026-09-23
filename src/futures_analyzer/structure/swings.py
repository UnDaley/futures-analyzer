"""Swing high / swing low tespiti ve HH/LH/HL/LL etiketleri.

Kural (N = length):
- Swing high: mumun high'ı solundaki N mumun hepsinden YÜKSEK ve sağındaki N mumdan DÜŞÜK DEĞİL.
- Swing low : mumun low'u solundaki N mumun hepsinden DÜŞÜK ve sağındaki N mumdan YÜKSEK DEĞİL.
Aynı seviyede art arda iki tepe varsa ilki swing sayılır.

Bir swing ancak sağındaki N mum kapandıktan sonra kesinleşir. Bu yüzden her swing'in
`confirmed_index` değeri vardır; analizde swing'i ancak o mumdan itibaren kullanabiliriz.
Böylece geçmişe dönük testlerde "geleceği görme" hatası olmaz.
"""

import pandas as pd

HIGH = "high"
LOW = "low"


def find_swings(df: pd.DataFrame, length: int = 3) -> pd.DataFrame:
    """Swing noktalarını zaman sırasıyla döndürür.

    Kolonlar: ts, kind ("high"/"low"), price, bar_index, confirmed_index, confirmed_ts, label
    """
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    rows = []

    for i in range(length, len(df) - length):
        left_highs, right_highs = highs[i - length:i], highs[i + 1:i + length + 1]
        if highs[i] > left_highs.max() and highs[i] >= right_highs.max():
            rows.append({"kind": HIGH, "price": float(highs[i]), "bar_index": i})

        left_lows, right_lows = lows[i - length:i], lows[i + 1:i + length + 1]
        if lows[i] < left_lows.min() and lows[i] <= right_lows.min():
            rows.append({"kind": LOW, "price": float(lows[i]), "bar_index": i})

    for row in rows:
        row["ts"] = df.index[row["bar_index"]]
        row["confirmed_index"] = row["bar_index"] + length
        row["confirmed_ts"] = df.index[row["confirmed_index"]]
    add_labels(rows)

    columns = ["ts", "kind", "price", "bar_index", "confirmed_index", "confirmed_ts", "label"]
    swings = pd.DataFrame(rows, columns=columns)
    # pandas etiketi olmayan (None) değerleri NaN'a çevirebilir; None olarak kalmasını sağlıyoruz.
    swings["label"] = swings["label"].astype(object).where(swings["label"].notna(), None)
    return swings


def add_labels(rows: list[dict]) -> None:
    """Her swing'i bir önceki aynı türden swing ile karşılaştırıp "label" ekler.

    Swing high: HH (daha yüksek), LH (daha düşük), EH (eşit)
    Swing low : HL (daha yüksek), LL (daha düşük), EL (eşit)
    İlk swing high ve ilk swing low'un karşılaştıracağı önceki swing yoktur (None).
    """
    previous = {HIGH: None, LOW: None}
    for row in rows:
        kind, price = row["kind"], row["price"]
        before = previous[kind]
        if before is None:
            row["label"] = None
        elif price == before:
            row["label"] = "EH" if kind == HIGH else "EL"
        elif kind == HIGH:
            row["label"] = "HH" if price > before else "LH"
        else:
            row["label"] = "HL" if price > before else "LL"
        previous[kind] = price
