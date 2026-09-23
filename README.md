# Futures Analyzer

NQ, ES ve GC futures piyasaları için analiz asistanı.

**Otomatik işlem yapmaz.** Broker'a emir göndermez. Sadece veri toplar, analiz eder ve senaryo raporu üretir. Son karar kullanıcıya aittir.

## Durum

- Faz 1 (piyasa verisi toplama) tamamlandı.
- Faz 2 (teknik göstergeler) tamamlandı: EMA 20/50/100/200, RSI 14, MACD, ATR 14, seans VWAP'ı, hacim ortalaması, EMA trendi.

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
uv run python -m futures_analyzer.cli indicators NQ               # göstergeler (JSON)

uv run uvicorn futures_analyzer.api:app --reload
curl "localhost:8000/candles?symbol=NQ&tf=1h&limit=5"
curl "localhost:8000/indicators?symbol=NQ"
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
