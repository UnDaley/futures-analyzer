# Futures Analyzer

NQ, ES ve GC futures piyasaları için analiz asistanı.

**Otomatik işlem yapmaz.** Broker'a emir göndermez. Sadece veri toplar, analiz eder ve senaryo raporu üretir. Son karar kullanıcıya aittir.

## Durum

Faz 1 (piyasa verisi toplama) tamamlandı.

## Kurulum

42 bilgisayarlarında home kotası küçük olduğu için Python ortamı `/goinfre`'de tutulur.
`~/.zshrc` dosyasında şu iki satır olmalı:

```bash
export UV_CACHE_DIR=/goinfre/$USER/.uv-cache
export UV_PROJECT_ENVIRONMENT=/goinfre/$USER/venvs/futures-analyzer
```

`/goinfre` bilgisayara özeldir. Başka bir bilgisayarda ortamı yeniden kurmak için `uv sync` yeterlidir.

```bash
cp .env.example .env
docker compose up -d        # PostgreSQL
uv sync                     # paketler
```

## Kullanım

```bash
uv run python -m futures_analyzer.cli fetch NQ                     # bütün zaman dilimleri
uv run python -m futures_analyzer.cli fetch NQ --timeframe 1h      # sadece 1h (+ 4h)
uv run python -m futures_analyzer.cli show NQ --timeframe 4h --limit 10

uv run uvicorn futures_analyzer.api:app --reload
curl "localhost:8000/candles?symbol=NQ&tf=1h&limit=5"
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
