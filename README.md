# Futures Analyzer

NQ, ES ve GC futures piyasaları için analiz asistanı.

**Otomatik işlem yapmaz.** Broker'a emir göndermez. Sadece veri toplar, analiz eder ve senaryo raporu üretir. Son karar kullanıcıya aittir.

## Durum

- Faz 1 (piyasa verisi toplama) tamamlandı.
- Faz 2 (teknik göstergeler) tamamlandı: EMA 20/50/100/200, RSI 14, MACD, ATR 14, seans VWAP'ı, hacim ortalaması, EMA trendi.
- Faz 3 (market structure) tamamlandı: swing high/low, HH/HL/LH/LL, BOS, CHoCH.
- Faz 4 (destek/direnç) tamamlandı: PDH/PDL, PWH/PWL, seans high/low, VWAP, swing'ler, round number, zone'lar.
- Faz 5 (seans analizi) tamamlandı: Asya/Londra/New York high-low, NY açılışı, önceki NY high-low.
- Faz 6 (likidite / price action) tamamlandı: BSL/SSL, equal high/low, sweep, FVG, displacement, order block, premium/discount.

## Kurulum

Gerekenler: Git, [uv](https://docs.astral.sh/uv/getting-started/installation/), Docker.

```bash
git clone https://github.com/UnDaley/futures-analyzer.git
cd futures-analyzer
cp .env.example .env
docker compose up -d        # PostgreSQL
uv sync                     # paketler
uv run python -m futures_analyzer.cli fetch NQ   # veriyi çek (ES ve GC için de)
```

Veritabanı her bilgisayarda ayrıdır. Yeni bir bilgisayarda `fetch` ile veri yeniden çekilir.

### 42 bilgisayarlarında

Home kotası küçük olduğu için Python ortamı `/goinfre`'de tutulur.
`uv sync`'ten önce `~/.zshrc` dosyasına şu iki satırı ekleyin ve yeni bir terminal açın:

```bash
export UV_CACHE_DIR=/goinfre/$USER/.uv-cache
export UV_PROJECT_ENVIRONMENT=/goinfre/$USER/venvs/futures-analyzer
```

`/goinfre` bilgisayara özeldir. Başka bir 42 bilgisayarında `uv sync` ortamı yeniden kurar.

## Kullanım

```bash
uv run python -m futures_analyzer.cli fetch NQ                     # bütün zaman dilimleri
uv run python -m futures_analyzer.cli fetch NQ --timeframe 1h      # sadece 1h (+ 4h)
uv run python -m futures_analyzer.cli show NQ --timeframe 4h --limit 10
uv run python -m futures_analyzer.cli snapshot NQ                 # göstergeler, structure, seviyeler (JSON)

uv run uvicorn futures_analyzer.api:app --reload
curl "localhost:8000/candles?symbol=NQ&tf=1h&limit=5"
curl "localhost:8000/snapshot?symbol=NQ"
```

## Testler

```bash
uv run pytest               # internetsiz birim testleri
uv run pytest -m network    # gerçek yfinance verisiyle test
```

## Veri notları

- Kaynak: yfinance. Veri 10-15 dakika gecikmelidir.
- Geçmiş sınırları: 5m/15m yaklaşık 60 gün, 1h yaklaşık 2 yıl, 1d 5 yıl.
- `NQ=F` gibi semboller en yakın vadeli kontrattır, vade geçişlerinde fiyat sıçrayabilir.
- Zamanlar veritabanında UTC saklanır.
- 4H mumlar 1H'den üretilir ve New York saatiyle 18:00'e (CME seans açılışı) hizalıdır.
- Erken kapanan tatil günlerinde yfinance 1H mumları 09:30'a hizalar.
- yfinance'in son satırı henüz dolmamış mumdur (hacmi 0 olabilir). Snapshot'taki `last_bar_complete` bunu gösterir.
- GC 1H verisinde seansın 18:00 mumunun hacmi genelde 0 gelir.

## Gösterge notları

- RSI ve ATR, TradingView ile aynı Wilder ortalamasını (ta.rma) kullanır. Değerler `ta` kütüphanesiyle birebir karşılaştırıldı.
- VWAP her seans açılışında (New York 18:00) sıfırlanır ve sadece 1h, 15m, 5m için hesaplanır.
- Yeterli veri yoksa değer `null` olur, tahmin edilmez.

## Market structure kuralları

- Swing high: high'ı solundaki 3 mumdan yüksek, sağındaki 3 mumdan düşük olmayan mum (swing low tersi). Swing ancak sağdaki 3 mum kapanınca kesinleşir.
- Etiketler: her swing bir önceki aynı türden swing ile karşılaştırılır (HH/LH/EH, HL/LL/EL).
- BOS/CHoCH: kapanış son kırılmamış swing'in ötesine geçerse kırılım olur. Trend yönündeyse BOS, tersiyse CHoCH. İğneler sayılmaz.
- Yapı sadece kapanmış mumlarla hesaplanır. Geçmiş olaylar sonradan gelen veriyle değişmez (testle doğrulandı).
- `trend_by_breaks` son kırılımın yönüdür, `swing_pattern` son swing etiketleridir. Etiketler yeni swing oluşana kadar geriden gelir; `price_position` fiyatın son swing'lere göre yerini gösterir.

## Destek / direnç

- PDH/PDL, PWH/PWL ve seans high/low 1H mumlardan, CME seansına (NY 18:00-17:00) göre hesaplanır. yfinance'in günlük verisi vade geçişi (roll) haftalarında farklı kontrata bakabildiği için kullanılmaz.
- Seviyeler: referanslar, 5m seans VWAP'ı, son 10 adet 1H ve 4H swing, en yakın round number'lar (NQ 100, ES 25, GC 25).
- 1H ATR'nin çeyreğinden yakın seviyeler tek zone'da birleşir; `strength` zone'daki farklı kaynak sayısıdır.

## Seanslar (New York saati)

| Seans | Saat |
|---|---|
| Asya | 18:00-03:00 |
| Londra | 03:00-08:00 |
| New York | 08:00-17:00 |

NY açılışı NQ/ES için 09:30, GC için 08:20 (COMEX). Seanslar New York saatine göre tanımlıdır, yaz saati değişimleri otomatik uygulanır. `taken` alanı bir seansın high/low'unun sonraki seanslarda aşılıp aşılmadığını gösterir. Seans seviyeleri destek/direnç zone'larına da eklenir.

## Likidite / price action (1H ve 15M, son 500 kapanmış mum)

- BSL/SSL: aşılmamış swing high/low'lar; ATR'nin 0,1'i kadar yakın olanlar equal high/low olarak birleşir.
- Sweep: iğne seviyeyi aşar ama mum içeride kapanır. Dışarıda kapanış kırılımdır, sweep değildir.
- FVG (imbalance): 3 mumlu boşluk; open / partial durumdakiler raporlanır, dolanlar raporlanmaz.
- Displacement: gövdesi önceki ATR'nin 1,5 katından büyük, gövde/aralık oranı en az %60 olan mum.
- Order block: displacement'tan önceki son ters renkli mum; fresh / tested, ötesinde kapanış olursa geçersiz.
- Premium/discount: son 30 adet 4H mumun aralığında fiyatın yüzdesi (>%55 premium, <%45 discount).
