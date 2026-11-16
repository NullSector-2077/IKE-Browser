# Workflow helper: PyQt6 and Qt from PyPI in the versions of versions.json,
# and FFmpeg to make the test clips. FFmpeg is used on the runner only; it is
# not part of I.K.E.
$ErrorActionPreference = "Stop"
$v = Get-Content (Join-Path $PSScriptRoot "versions.json") -Raw | ConvertFrom-Json
python -m pip install --disable-pip-version-check `
    "PyQt6==$($v.pyqt.'PyQt6')" "PyQt6-Qt6==$($v.pyqt.'PyQt6-Qt6')" `
    "PyQt6-WebEngine==$($v.pyqt.'PyQt6-WebEngine')" `
    "PyQt6-WebEngine-Qt6==$($v.pyqt.'PyQt6-WebEngine-Qt6')" websocket-client
if ($LASTEXITCODE -ne 0) { throw "pip failed" }
python -m pip list

if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    choco install ffmpeg -y --no-progress
    if ($LASTEXITCODE -ne 0) { throw "could not install FFmpeg" }
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + $env:Path
}
$ffmpeg = (Get-Command ffmpeg -ErrorAction SilentlyContinue).Source
if (-not $ffmpeg) {
    $ffmpeg = Get-ChildItem "C:\ProgramData\chocolatey\bin\ffmpeg.exe" -ErrorAction Stop | Select-Object -ExpandProperty FullName
}
# for the steps that follow
Split-Path $ffmpeg | Out-File -FilePath $env:GITHUB_PATH -Encoding utf8 -Append
& $ffmpeg -version | Select-Object -First 1
