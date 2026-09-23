#!/usr/bin/env bash
# Futures Analyzer'ı başlatır: veritabanı + dashboard. Tarayıcı kendiliğinden açılır.
# Veriler sunucu açılınca ve sonra 15 dakikada bir arka planda güncellenir.
# Kapatmak için bu pencerede Ctrl+C.
# --pause: kısayoldan açılınca pencere hemen kapanmasın (hata mesajı okunabilsin)
set -e
if [ "$1" = "--pause" ]; then
  trap 'echo; read -r -p "Kapatmak için Enter tuşuna basın..."' EXIT
fi
cd "$(dirname "$0")"
PORT=8000
URL="http://localhost:$PORT"

# 42 bilgisayarları: home kotası küçük, Python ortamı /goinfre'de tutulur
if [ -d "/goinfre/$USER" ]; then
  export UV_CACHE_DIR="/goinfre/$USER/.uv-cache"
  export UV_PROJECT_ENVIRONMENT="/goinfre/$USER/venvs/futures-analyzer"
fi

open_browser() {
  xdg-open "$URL" >/dev/null 2>&1 || open "$URL" >/dev/null 2>&1 || echo "Tarayıcıda açın: $URL"
}

if curl -s "$URL/health" >/dev/null 2>&1; then
  echo "Futures Analyzer zaten çalışıyor: $URL"
  open_browser
  exit 0
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "HATA: 'uv' bulunamadı. Kurulum: https://docs.astral.sh/uv/getting-started/installation/"
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "HATA: Docker çalışmıyor. Docker'ı (Docker Desktop) başlatıp tekrar deneyin."
  exit 1
fi

[ -f .env ] || cp .env.example .env

echo "1/3 Veritabanı başlatılıyor..."
docker compose up -d
for _ in $(seq 1 30); do
  docker compose exec -T postgres pg_isready -U futures >/dev/null 2>&1 && break
  sleep 1
done

echo "2/3 Python paketleri kontrol ediliyor..."
uv sync -q

echo "3/3 Dashboard başlatılıyor: $URL"
echo "    Veriler arka planda güncelleniyor (ilk seferde birkaç dakika sürer)."
echo "    Kapatmak için bu pencerede Ctrl+C."
# Sunucu hazır olunca tarayıcıyı aç
( for _ in $(seq 1 60); do curl -s "$URL/health" >/dev/null 2>&1 && { open_browser; break; }; sleep 1; done ) &
uv run uvicorn futures_analyzer.api:app --port "$PORT" || true
