# Futures Analyzer'ı başlatır (Windows): veritabanı + dashboard, tarayıcı kendiliğinden açılır.
# Veriler sunucu açılınca ve sonra 15 dakikada bir arka planda güncellenir.
# Kapatmak için bu pencerede Ctrl+C.

$Project = Split-Path -Parent $PSScriptRoot
Set-Location $Project
$Url = "http://localhost:8000"

function Test-Server {
    try { Invoke-WebRequest "$Url/health" -UseBasicParsing -TimeoutSec 2 | Out-Null; return $true }
    catch { return $false }
}

function Stop-WithMessage($Message) {
    Write-Host ""
    Write-Host $Message -ForegroundColor Red
    Read-Host "Kapatmak için Enter tuşuna basın"
    exit 1
}

if (Test-Server) {
    Write-Host "Futures Analyzer zaten çalışıyor: $Url"
    Start-Process $Url
    exit 0
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Stop-WithMessage "HATA: 'uv' bulunamadı. Kurulum: https://docs.astral.sh/uv/getting-started/installation/"
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Stop-WithMessage "HATA: Docker bulunamadı. Docker Desktop'ı kurun: https://www.docker.com/products/docker-desktop/"
}
docker info 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Stop-WithMessage "HATA: Docker çalışmıyor. Docker Desktop'ı açın, 'Engine running' yazınca tekrar deneyin."
}

if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env" }

Write-Host "1/3 Veritabanı başlatılıyor..."
docker compose up -d
if ($LASTEXITCODE -ne 0) { Stop-WithMessage "HATA: Veritabanı başlatılamadı (yukarıdaki mesaja bakın)." }
for ($i = 0; $i -lt 30; $i++) {
    docker compose exec -T postgres pg_isready -U futures 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { break }
    Start-Sleep -Seconds 1
}

Write-Host "2/3 Python paketleri kontrol ediliyor (ilk seferde birkaç dakika sürebilir)..."
uv sync -q
if ($LASTEXITCODE -ne 0) { Stop-WithMessage "HATA: Python paketleri kurulamadı (yukarıdaki mesaja bakın)." }

Write-Host "3/3 Dashboard başlatılıyor: $Url"
Write-Host "    Veriler arka planda güncelleniyor (ilk seferde birkaç dakika sürer)."
Write-Host "    Kapatmak için bu pencerede Ctrl+C."

# Sunucu hazır olunca tarayıcıyı aç (arka planda)
Start-Job -ArgumentList $Url -ScriptBlock {
    param($u)
    for ($i = 0; $i -lt 60; $i++) {
        try { Invoke-WebRequest "$u/health" -UseBasicParsing -TimeoutSec 2 | Out-Null; Start-Process $u; break }
        catch { Start-Sleep -Seconds 1 }
    }
} | Out-Null

uv run uvicorn futures_analyzer.api:app --port 8000
Read-Host "Program kapandı. Pencereyi kapatmak için Enter tuşuna basın"
