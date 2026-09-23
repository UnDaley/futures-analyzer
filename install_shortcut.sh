#!/usr/bin/env bash
# Masaüstüne ve uygulama menüsüne "Futures Analyzer" kısayolu ekler (Linux / GNOME).
# Kısayola çift tıklayınca bir terminal penceresinde start.sh çalışır.
set -e
PROJECT="$(cd "$(dirname "$0")" && pwd)"
chmod +x "$PROJECT/start.sh"

ENTRY="[Desktop Entry]
Type=Application
Name=Futures Analyzer
Comment=Futures piyasa analiz asistanı (işlem açmaz)
Exec=bash -l \"$PROJECT/start.sh\" --pause
Icon=utilities-system-monitor
Terminal=true
Categories=Office;Finance;"

mkdir -p "$HOME/.local/share/applications"
echo "$ENTRY" > "$HOME/.local/share/applications/futures-analyzer.desktop"
echo "Uygulama menüsüne eklendi (Futures Analyzer diye aratın)."

DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
if [ -d "$DESKTOP_DIR" ]; then
  FILE="$DESKTOP_DIR/futures-analyzer.desktop"
  echo "$ENTRY" > "$FILE"
  chmod +x "$FILE"
  # GNOME'da çift tıklamayla çalışması için "güvenilir" işaretle
  gio set "$FILE" metadata::trusted true 2>/dev/null || true
  echo "Masaüstüne eklendi: $FILE"
  echo "İlk açılışta 'Başlatmaya izin ver' (Allow Launching) seçmeniz gerekebilir."
fi
