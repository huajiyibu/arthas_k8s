# 下载并解压 Arthas 工具到 <项目根>/arthas/arthas/arthas
# 用法：在项目根目录执行  powershell -ExecutionPolicy Bypass -File scripts\download_arthas.ps1
$ErrorActionPreference = "Stop"

$root   = Split-Path -Parent $PSScriptRoot          # scripts 的上一级 = 项目根
$dest   = Join-Path $root "arthas\arthas"           # 工具父目录（config.py 的默认 ARTHAS_PARENT_DIR）
$url    = "https://github.com/alibaba/arthas/releases/latest/download/arthas-bin.zip"
$tmpZip = Join-Path $env:TEMP "arthas-bin.zip"

Write-Host "下载 Arthas: $url"
curl.exe -L -o $tmpZip $url
if (-not (Test-Path $tmpZip)) { throw "下载失败，请检查网络（可能需要代理）" }

Write-Host "解压到 $dest"
New-Item -ItemType Directory -Force -Path $dest | Out-Null
Expand-Archive -Path $tmpZip -DestinationPath $dest -Force
Remove-Item $tmpZip -Force

# arthas-bin.zip 解压后可能带一层子目录（如 arthas-bin），统一整理成 $dest\arthas
$boot = Get-ChildItem -Path $dest -Recurse -Filter arthas-boot.jar -ErrorAction SilentlyContinue | Select-Object -First 1
if ($boot) {
    $target = Join-Path $dest "arthas"
    if ($boot.Directory.FullName -ne $target) {
        Remove-Item $target -Recurse -Force -ErrorAction SilentlyContinue
        Move-Item $boot.Directory.FullName $target
    }
}

if (Test-Path (Join-Path $dest "arthas\arthas-boot.jar")) {
    Write-Host "完成 ✅ Arthas 工具位于: $dest\arthas"
} else {
    Write-Host "⚠️ 未找到 arthas-boot.jar，请检查解压结果：$dest"
}
