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
- Faz 7 (makro) tamamlandı: Fed faizi, 2Y/10Y, eğri, reel faiz, CPI/PPI/PCE, NFP, işsizlik, GSYH (FRED).
- Faz 8 (intermarket) tamamlandı: ES/NQ/YM/RTY/DXY/US10Y/US02Y/VIX (NQ, ES), DXY/US10Y/reel faiz/SI (GC), korelasyon, SMT.
- Faz 9 (haber ve ekonomik takvim) tamamlandı: olay riski, yeni açıklanan veriler, resmi kaynaklardan haberler.
- Faz 10 (senaryo motoru ve skor) tamamlandı: ağırlıklı skor, bullish/bearish/neutral senaryolar.
- Faz 11 (Claude entegrasyonu) tamamlandı: standart formatta Türkçe rapor, uydurma fiyat kontrolü.
- Faz 12 (backtest / değerlendirme) tamamlandı: analiz günlüğü, sonuç ölçümü, geçmişe dönük backtest.
- Faz 13 (dashboard) tamamlandı: grafik, senaryo seviyeleri, skor, olay riski, rapor ve analiz geçmişi.

## Günlük kullanım

```bash
docker compose up -d
uv run python -m futures_analyzer.cli fetch-all      # bütün veriyi güncelle (birkaç dakika)
uv run uvicorn futures_analyzer.api:app              # dashboard: http://localhost:8000
uv run python -m futures_analyzer.cli record         # analizleri kaydet (sonuç ölçümü için)
uv run python -m futures_analyzer.cli evaluate       # 1 gün sonra: sonuçları ölç
```

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
uv run python -m futures_analyzer.cli fetch-macro                  # makro veriler (FRED)
uv run python -m futures_analyzer.cli fetch-intermarket            # YM, RTY, DXY, US10Y, VIX, SI (1h)
uv run python -m futures_analyzer.cli fetch-news                   # haberler + ekonomik takvim
uv run python -m futures_analyzer.cli fetch-all                    # hepsini tek seferde çek
uv run python -m futures_analyzer.cli show NQ --timeframe 4h --limit 10
uv run python -m futures_analyzer.cli snapshot NQ                 # bütün analiz verisi (JSON)
uv run python -m futures_analyzer.cli report NQ                   # Claude raporu (ANTHROPIC_API_KEY gerekir, kaydedilir)
uv run python -m futures_analyzer.cli prompt NQ                   # API anahtarı olmadan: claude.ai için prompt dosyası
uv run python -m futures_analyzer.cli check-report 4 rapor.txt    # claude.ai raporunu kontrol et ve kaydet
uv run python -m futures_analyzer.cli record                      # analizleri Claude'suz kaydet
uv run python -m futures_analyzer.cli evaluate                    # kayıtların sonuçlarını ölç ve özetle
uv run python -m futures_analyzer.cli backtest NQ --days 50 --step 4h --csv nq.csv

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

## Makro (FRED)

API anahtarı gerekmez. Faizler günlük (genelde 1 iş günü gecikmeli), enflasyon ve istihdam aylık güncellenir; her değerin tarihi snapshot'ta verilir. Enflasyon endeksleri yıllık % değişim (YoY) olarak, NFP aylık değişim (bin kişi) olarak raporlanır. Not: FRED özel User-Agent içeren istekleri reddediyor.

## Intermarket

Her ilişkili varlığın günlük değişimi (faizlerde baz puan) önceki işlem günü kapanışına göre hesaplanır ve beklenen ilişkiye (+1 aynı yön, -1 ters yön) göre kontratın hareketini doğrulayıp (`confirms`) doğrulamadığı (`diverges`) belirtilir. `correlation_20d` ilişkinin gerçekten sürüp sürmediğini gösterir. SMT: eş varlıklardan (NQ-ES, GC-SI) biri önceki gün high/low'unu alıp diğeri alamadıysa uyumsuzluk işaretlenir. 2 yıllık faiz ve reel faiz FRED'den gelir (1 iş günü gecikmeli olabilir, tarihi belirtilir).

## Haber ve ekonomik takvim

- Takvim: faireconomy.media (Forex Factory) haftalık JSON, sadece ABD'nin yüksek/orta etkili olayları. Resmi değildir; saatte bir güncellenir ve sık istekleri geçici olarak reddeder (HTTP 429), bu durumda veritabanındaki son takvim kullanılır. `calendar_manual.json` dosyasına aynı biçimde elle olay eklenebilir.
- `event_risk`: en yakın yüksek etkili olay, kaç dakika kaldığı ve neden önemli olduğu. 60 dakikadan azsa `imminent: true`.
- Haberler: Fed basın açıklamaları, Fed konuşmaları, BEA (RSS). BLS ve CNBC otomatik erişimi engelliyor. Yeni kaynak `news/feeds.py` içindeki `FEEDS` sözlüğüne eklenebilir.
- Haber etkisi başlıktaki anahtar kelimelere göre kaba bir sınıflandırmadır (`confidence: low`); yönü belirsiz olanlar `unclear` olarak işaretlenir.
- Siteler User-Agent başlığına farklı tepki verdiği için bütün istekler `http.py` üzerinden yapılır.

## Skor ve senaryolar

Skor Python'da hesaplanır; her bileşen -1 (bearish) ile +1 (bullish) arası bir değer alır ve ağırlığıyla çarpılır:

| Bileşen | Ağırlık | Nasıl |
|---|---|---|
| Trend | 20 | EMA trendi: 1D %40, 4H %35, 1H %25 |
| Market structure | 20 | Son BOS/CHoCH yönü: 4H %50, 1H %30, 15M %20 |
| Likidite | 15 | Premium/discount, son sweep, son displacement |
| Hacim | 10 | Son 5 kapanmış 1H mumda yükselen/düşen mum hacmi dengesi |
| VWAP | 10 | 15M fiyat seans VWAP'ının üstünde/altında |
| Makro | 10 | 10Y faizin (GC için reel faizin) 20 günlük değişimi; artış olumsuz |
| Intermarket | 10 | İlişkili varlıkların bugünkü yönü, SMT uyumsuzluğu |
| Haber | 5 | Son 24 saatte yönlü başlıklar (düşük güven) |

Toplam -100 ile +100 arasıdır; |toplam| < 15 ise bias nötrdür. Skor olasılık değildir, kanıtların yön uyumudur. `coverage` kaç puanlık ağırlığın gerçekten hesaplanabildiğini gösterir.

Senaryolar: tetik = en yakın direnç/destek zone'unun kenarı (fiyat bir zone'un içindeyse o zone), hedefler = tetikten ve birbirinden en az yarım ATR uzak sonraki iki zone, invalidation = karşı tetik. Her senaryonun risk faktörleri, ona ters düşen skor bileşenleri ve olay riskidir.

## Claude raporu

### API anahtarı olmadan (claude.ai ile, ek ücret yok)

1. `uv run python -m futures_analyzer.cli prompt NQ` analizi kaydeder ve `prompts/NQ_<no>.txt` dosyasını yazar (talimatlar + veri).
2. Dosyanın içeriğinin tamamını claude.ai'de yeni bir sohbete yapıştırın.
3. Claude'un raporunu bir metin dosyasına kaydedin, örn. `prompts/rapor.txt`.
4. `uv run python -m futures_analyzer.cli check-report <no> prompts/rapor.txt` rapordaki fiyatları veriyle karşılaştırır ve raporu analiz kaydına ekler (dashboard'da görünür). Veride olmayan fiyat varsa Claude'a yapıştırılacak düzeltme mesajını yazdırır.

`prompts/` klasörü GitHub'a gönderilmez.

### API anahtarıyla (otomatik)

`report` komutu snapshot'ı Claude'a gönderir ve standart formatta Türkçe rapor yazdırır. Anahtar `.env` dosyasına `ANTHROPIC_API_KEY=...` olarak eklenir; model `ANTHROPIC_MODEL` ile değiştirilebilir (varsayılan `claude-opus-5`).

- Bütün hesaplamalar Python'da yapılır; Claude yalnızca yorumlar. System prompt veride olmayan seviye, olasılık veya değer yazmayı yasaklar ve al/sat tavsiyesi vermez.
- Rapordaki fiyat gibi görünen her sayı (güncel fiyatın ±%30'u) snapshot'taki değerlerle bir tick toleransla karşılaştırılır. Bilinmeyen sayı varsa Claude'dan bir kez düzeltmesi istenir; hâlâ varsa rapor "doğrulanmadı" olarak işaretlenir ve sayılar listelenir.
- İstek güvenlik sınıflandırıcısı tarafından reddedilirse sunucu tarafı fallback (`fallbacks: "default"`) devreye girer.
- System prompt sabittir ve önbelleğe alınır; adaptive thinking ve streaming kullanılır.

## Backtest ve değerlendirme

- `report` ve `record` her analizi `analyses` tablosuna kaydeder. `evaluate` zamanı gelen kayıtlar için 1s / 4s / 1g sonraki fiyat değişimini, bias'ın 4 saatlik yön isabetini ve 1 gün içinde hangi senaryonun tetiklenip hedefe mi invalidation'a mı gittiğini ölçer.
- `backtest` analiz motorunu geçmişteki anlara o anda bilinen veriyle uygular (Claude kullanılmaz). Canlı analizle aynı `build_snapshot` fonksiyonu kullanılır; `now` sonrasındaki verinin sonucu değiştirmediği testle doğrulanır.
- Sınırlar: 5m veri ~60 gün olduğu için en fazla ~55 gün geriye gidilebilir; geçmiş haberler dahil edilmez; aylık makro veriler gözlem tarihine göre filtrelenir (gerçek yayın tarihi daha sonradır). 4 saatlik adımlarla gözlemler birbiriyle örtüşür, bu yüzden örneklem gerçekte göründüğünden küçüktür.
- Başarı ölçütü raporun ne kadar ikna edici yazıldığı değil, bu tablolardır. Her satır `baseline` (sinyal kullanmadan bütün analizler) ile karşılaştırılmalıdır.

İlk ölçüm (3 Ağustos - 22 Eylül 2026, 4 saatlik adım, 180 analiz; başlangıç ağırlıklarıyla):

| Kontrat | Baseline 4s isabet | Bullish bias 4s isabet | Bearish bias 4s isabet | Birincil senaryo hedefe ulaşma |
|---|---|---|---|---|
| NQ | %48,3 | %46,8 | %51,3 | %48,4 |
| ES | %54,4 | %53,7 | %55,6 | %46,0 |
| GC | %51,4 | %55,7 | %45,7 | %66,1 |

Yorum: NQ ve ES için skorun baseline'a göre anlamlı bir avantajı görünmüyor; GC'deki fark küçük örneklem nedeniyle henüz güvenilir değil. Ağırlıklar ve kurallar bu ölçümlere göre ayarlanmalı.

## Dashboard

`uv run uvicorn futures_analyzer.api:app` ile açılır: http://localhost:8000

- Grafik: TradingView Lightweight Charts (CDN). Mumlar, Python'da hesaplanan EMA 20/50/200 ve seans VWAP'ı, senaryo tetik ve hedef çizgileri. Saatler New York saatidir.
- Yan panel: skor ve bileşenleri, olay riski, senaryolar, seanslar, destek/direnç zone'ları.
- "Claude raporu üret" düğmesi raporu üretir ve kaydeder (API anahtarı gerekir).
- Analiz geçmişi tablosu kayıtlı analizlerin ölçülen sonuçlarını gösterir. Sayfa dakikada bir yenilenir.
- Derleme adımı gerektirmeyen tek bir HTML dosyasıdır (`src/futures_analyzer/web/dashboard.html`). İleride React / Next.js'e geçilirse aynı API uç noktaları (`/chart`, `/snapshot`, `/analyses`, `/report`) kullanılabilir.

## Bilinçli olarak yapılmayanlar

- Otomatik emir, broker bağlantısı: yok ve eklenmeyecek.
- Redis: şu an ihtiyaç yok (hesaplar birkaç saniye sürüyor); önbellek gerekirse eklenecek.
- Gerçek zamanlı veri: yfinance gecikmeli; `DataProvider` arayüzüyle ücretli bir kaynak (örn. Databento) eklenebilir.
