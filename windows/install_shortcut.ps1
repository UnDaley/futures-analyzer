# Masaüstüne ve Başlat menüsüne "Futures Analyzer" kısayolu ekler (Windows).
$Project = Split-Path -Parent $PSScriptRoot
$Target = Join-Path $Project "windows\start.bat"
$Shell = New-Object -ComObject WScript.Shell

$Places = @(
    [Environment]::GetFolderPath("Desktop"),
    (Join-Path ([Environment]::GetFolderPath("StartMenu")) "Programs")
)
foreach ($Folder in $Places) {
    $Link = $Shell.CreateShortcut((Join-Path $Folder "Futures Analyzer.lnk"))
    $Link.TargetPath = $Target
    $Link.WorkingDirectory = $Project
    $Link.IconLocation = (Join-Path $Project "windows\icon.ico") + ",0"
    $Link.Description = "NQ / ES / GC için 10am modeli analiz asistanı (işlem açmaz)"
    $Link.Save()
    Write-Host "Kısayol eklendi: $Folder"
}
Write-Host ""
Write-Host "Tamam. Masaüstündeki 'Futures Analyzer' simgesine çift tıklayarak başlatabilirsiniz."
Read-Host "Kapatmak için Enter tuşuna basın"
