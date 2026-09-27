# Futures Analyzer — 10am Model

NQ, ES ve GC futures için Powell Trades'in 10am modelini takip eden analiz asistanı.

**Otomatik işlem yapmaz.** Broker'a emir göndermez. Veriyi toplar, modelin kurallarını uygular, bugünkü durumu ve geçmiş sonuçları gösterir. Son karar kullanıcıya aittir.

## Durum

- Faz 1-13: veri toplama, göstergeler, seanslar, ekonomik takvim, Claude raporu ve dashboard tamamlandı.
- Faz 14 (10am modeli): skor ve senaryo motoru kaldırıldı; sistem tamamen 10am modeline odaklandı. Makro, intermarket, likidite/price action, destek/direnç ve market structure modülleri de kaldırıldı (git geçmişinde duruyor). Dashboard daha okunabilir olacak şekilde yeniden tasarlandı.

## Günlük kullanım (terminalsiz)

1. Masaüstündeki **Futures Analyzer** kısayoluna çift tıklayın (veya uygulama menüsünde aratın). Açılan pencere sunucudur; açık kalsın.
2. Tarayıcıda dashboard açılır (http://localhost:8000). Veriler açılışta ve 15 dakikada bir kendiliğinden güncellenir.
3. Üstten kontratı seçin. "Bugünkü setup" kartı modelin hangi adımda olduğunu ve şu an neyi beklediğini yazar; grafikte 10:00 açılışı, manipülasyon, giriş, stop ve hedef işaretlidir.
4. "Geçmiş performans" aynı kuralların son günlerdeki sonuçlarını gösterir (her açılışta 5M veriden yeniden hesaplanır).
5. Claude raporu (isteğe bağlı): "Claude raporu" bölümünü açıp 3 adımı izleyin.
6. Kapatmak için sunucu penceresinde Ctrl+C.

Kısayol yoksa (yeni bilgisayar) bir kez: `./install_shortcut.sh`. Kısayol olmadan başlatmak için: `./start.sh`.
İlk açılışta GNOME "Başlatmaya izin ver" (Allow Launching) sorabilir.

Ayarlar (`.env`): `AUTO_REFRESH_MINUTES=15` (0 = otomatik güncelleme kapalı).

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

### Windows (kişisel bilgisayar)

Bir kez kurulum:

1. **Git**: https://git-scm.com/download/win (varsayılan seçeneklerle kurun).
2. **Docker Desktop**: https://www.docker.com/products/docker-desktop/ — kurulumda WSL 2 seçili kalsın; bilgisayarı yeniden başlatmanız istenebilir. Docker Desktop'ı açıp "Engine running" yazısını görün.
3. **uv**: PowerShell'i açıp şunu çalıştırın, sonra PowerShell'i kapatıp yeniden açın:
   `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
4. Projeyi indirin (repo private olduğu için tarayıcıda GitHub girişi istenir):
   `git clone https://github.com/UnDaley/futures-analyzer.git`
5. `futures-analyzer\windows\install_shortcut.bat` dosyasına çift tıklayın. Masaüstüne ve Başlat menüsüne **Futures Analyzer** kısayolu eklenir.

Günlük kullanım: Docker Desktop açıkken masaüstündeki **Futures Analyzer** kısayoluna çift tıklayın; gerisi Linux'takiyle aynı (dashboard tarayıcıda açılır). İlk açılışta Python paketlerinin kurulması ve verilerin çekilmesi birkaç dakika sürer. Windows Güvenlik Duvarı izin sorarsa "İzin ver" deyin.

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
uv run python -m futures_analyzer.cli fetch-news                   # ekonomik takvim
uv run python -m futures_analyzer.cli fetch-all                    # hepsini tek seferde çek
uv run python -m futures_analyzer.cli show NQ --timeframe 5m --limit 10
uv run python -m futures_analyzer.cli snapshot NQ                 # bugünkü setup, seviyeler, geçmiş (JSON)
uv run python -m futures_analyzer.cli history NQ --days 60 --csv nq.csv   # son günlerin 10am sonuçları
uv run python -m futures_analyzer.cli report NQ                   # Claude raporu (ANTHROPIC_API_KEY gerekir, kaydedilir)
uv run python -m futures_analyzer.cli prompt NQ                   # API anahtarı olmadan: claude.ai için prompt dosyası
uv run python -m futures_analyzer.cli check-report 4              # claude.ai raporunu yapıştır, kontrol et ve kaydet

uv run uvicorn futures_analyzer.api:app --reload
curl "localhost:8000/snapshot?symbol=NQ"
curl "localhost:8000/chart?symbol=NQ&tf=5m&limit=100"
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

## 10am modeli

Kurallar `src/futures_analyzer/strategy/ten_am.py` dosyasındadır; 5 dakikalık mumlarla, New York saatiyle uygulanır.

1. **Açılış**: 10:00 mumunun açılış fiyatı.
2. **Manipülasyon**: fiyat açılıştan en az eşik kadar uzaklaşır (NQ 15, ES 4, GC 3 puan; `instruments.py` içindeki `trap_points`). Yukarı manipülasyon short, aşağı manipülasyon long setup'ı hazırlar.
3. **Geri kırılım**: bir 5M mum açılışın öbür tarafında kapanır.
4. **Retest ve giriş**: sonraki bir mum açılışa geri dokunup kırılım tarafında kapanır; giriş = açılış fiyatı. Mum manipülasyon tarafında kapanırsa kırılım başarısız sayılır ve 3. adım yeniden beklenir.
5. **Stop**: manipülasyonun en uç noktası + 1 tick. **Hedef**: girişten en az 1R uzaktaki ilk alınmamış likidite (önceki gün, Asya, Londra, 08:00-10:00 yükseği/düşüğü, 10:00 sonrası tepe/dip, 5M swing'ler). Uygun seviye yoksa 2R.
6. Giriş 12:00'ye kadar oluşmazsa o gün setup yoktur. Açık işlem 16:00'da son kapanışla sonuçlandırılır.

Sonuç ölçümü:

- Hedefe veya stop'a iğneyle dokunmak yeterlidir. Aynı 5M mumda ikisine birden dokunulursa sonuç "belirsiz" sayılır (sıra bilinemez). Retest mumu stop'a da dokunduysa sonuç stop sayılır.
- Yalnızca kapanmış mumlar kullanılır; bir günün sonucu sonradan gelen veriyle değişmez (testle doğrulandı). Canlı durum ve geçmiş istatistikler aynı fonksiyonla hesaplanır.
- R = stop mesafesi. İstatistikler: setup sayısı, hedef/stop, kazanma oranı (hedef / (hedef + stop)), ortalama ve toplam R, long/short ayrımı.

Sınırlar:

- Model 5M mumlarla çalışır; popüler kullanımda 1M grafik tercih edilir. 1M'de retest ve stop sırası daha kesin görülür ama yfinance 1M veriyi yalnızca ~7 gün geriye verir.
- Veri 10-15 dakika gecikmelidir. Dashboard'daki canlı durum bu gecikmeyle gelir; işlem kararı için kendi platformunuzdaki fiyatı esas alın.
- Eşikler ve kurallar kaynaklardan derlenen varsayılanlardır; kendi uyguladığınız kurallardan farklıysa `ten_am.py` ve `instruments.py` içinden değiştirin.

İlk ölçüm (20 Temmuz - 24 Eylül 2026, 48 işlem günü, varsayılan kurallarla):

| Kontrat | Setup | Hedef / stop | Kazanma oranı | Ortalama R | Toplam R |
|---|---|---|---|---|---|
| NQ | 20 | 11 / 6 | %64,7 | +0,61 | +12,11 |
| ES | 21 | 9 / 11 | %45,0 | +0,16 | +3,31 |
| GC | 22 | 8 / 11 | %42,1 | +0,16 | +3,56 |

Örneklem küçüktür; bu sonuçlar kuralların gelecekte de aynı şekilde çalışacağını göstermez.

## Grafik göstergeleri

- Grafikte isteğe bağlı EMA 20/50/200 ve seans VWAP'ı gösterilebilir; 10am modeli bunları kullanmaz.
- VWAP her seans açılışında (New York 18:00) sıfırlanır ve sadece 1h, 15m, 5m için hesaplanır.

## Ekonomik takvim

- Kaynak: faireconomy.media (Forex Factory) haftalık JSON, sadece ABD'nin yüksek/orta etkili olayları. Resmi değildir; saatte bir güncellenir ve sık istekleri geçici olarak reddeder (HTTP 429), bu durumda veritabanındaki son takvim kullanılır. `calendar_manual.json` dosyasına aynı biçimde elle olay eklenebilir.
- Bugünkü olaylar listelenir; 10:00'a 30 dakikadan yakın olanlar (ISM, JOLTS, tüketici güveni...) manipülasyon hareketini doğrudan etkileyebileceği için işaretlenir.
- `event_risk`: en yakın yüksek etkili olay; 60 dakikadan azsa `imminent: true` ve dashboard'da uyarı şeridi çıkar.

## Claude raporu

### API anahtarı olmadan (claude.ai ile, ek ücret yok)

1. `uv run python -m futures_analyzer.cli prompt NQ` snapshot'ı kaydeder ve `prompts/NQ_<no>.txt` dosyasını yazar (talimatlar + veri).
2. Dosyanın içeriğinin tamamını claude.ai'de yeni bir sohbete yapıştırın.
3. Claude'un cevabını kopyalayın ve `uv run python -m futures_analyzer.cli check-report <no>` komutunu çalıştırıp terminale yapıştırın; bitince yeni satırda Ctrl+D. (Rapor bir dosyadaysa: `check-report <no> dosya.txt`.)
4. Komut rapordaki fiyatları veriyle karşılaştırır ve raporu kayda ekler (dashboard'da görünür). Veride olmayan fiyat varsa Claude'a yapıştırılacak düzeltme mesajını yazdırır.

`prompts/` klasörü GitHub'a gönderilmez.

### API anahtarıyla (otomatik)

`report` komutu snapshot'ı Claude'a gönderir ve standart formatta Türkçe 10am raporu yazdırır (durum, seviyeler, sıradaki adım, likidite, olay riski, geçmiş performans). Anahtar `.env` dosyasına `ANTHROPIC_API_KEY=...` olarak eklenir; model `ANTHROPIC_MODEL` ile değiştirilebilir (varsayılan `claude-opus-5`).

- Bütün hesaplamalar Python'da yapılır; Claude yalnızca yorumlar. Claude'a geçmiş istatistikler ve son 10 gün gider. System prompt veride olmayan seviye, olasılık veya değer yazmayı yasaklar ve al/sat tavsiyesi vermez.
- Rapordaki fiyat gibi görünen her sayı (güncel fiyatın ±%30'u) snapshot'taki değerlerle bir tick toleransla karşılaştırılır. Bilinmeyen sayı varsa Claude'dan bir kez düzeltmesi istenir; hâlâ varsa rapor "doğrulanmadı" olarak işaretlenir ve sayılar listelenir.
- İstek güvenlik sınıflandırıcısı tarafından reddedilirse sunucu tarafı fallback (`fallbacks: "default"`) devreye girer.
- System prompt sabittir ve önbelleğe alınır; adaptive thinking ve streaming kullanılır.

## Dashboard

`uv run uvicorn futures_analyzer.api:app` ile açılır: http://localhost:8000

- Bugünkü setup: durum etiketi, "şimdi ne bekleniyor" cümlesi, 4 adımlı kontrol listesi, giriş/stop/hedef/R:R.
- Grafik (TradingView Lightweight Charts, CDN): 5M/15M/1H mumlar, 10:00 açılışı, manipülasyon ucu, stop ve hedef çizgileri; manipülasyon, kırılım, giriş ve sonuç işaretleri. EMA/VWAP isteğe bağlı. Saatler New York saatidir.
- Geçmiş performans: istatistik kutuları ve gün gün sonuç tablosu. Bugünün seviyeleri ve ekonomik takvim yan panelde.
- Açık ve koyu temaya uyar; dar ekranda setup kartı en üstte gelir. Sayfa dakikada bir yenilenir.
- Derleme adımı gerektirmeyen tek bir HTML dosyasıdır (`src/futures_analyzer/web/dashboard.html`). API uç noktaları: `/snapshot`, `/chart`, `/reports`, `/prompt`, `/check-report`, `/report`, `/refresh`.

## Bilinçli olarak yapılmayanlar

- Otomatik emir, broker bağlantısı: yok ve eklenmeyecek.
- Redis: şu an ihtiyaç yok (snapshot 1 saniyenin altında hesaplanıyor).
- Gerçek zamanlı veri: yfinance gecikmeli; `DataProvider` arayüzüyle ücretli bir kaynak (örn. Databento) eklenebilir.
