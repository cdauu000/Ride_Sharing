$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$runtimePath = Join-Path $projectRoot 'artifacts/review/web-v2'
New-Item -ItemType Directory -Force -Path $runtimePath | Out-Null
foreach ($folder in @('app', 'components', 'lib', 'public')) {
    Copy-Item -LiteralPath (Join-Path 'web' $folder) -Destination $runtimePath -Recurse -Force
}
foreach ($file in @('package.json', 'package-lock.json', 'next.config.ts', 'next-env.d.ts', 'tsconfig.json')) {
    Copy-Item -LiteralPath (Join-Path 'web' $file) -Destination $runtimePath -Force
}
$modulesPath = Join-Path $runtimePath 'node_modules'
if (-not (Test-Path -LiteralPath $modulesPath)) {
    New-Item -ItemType Junction -Path $modulesPath -Target (Join-Path $projectRoot 'web/node_modules') | Out-Null
}
$env:RISE_LOCAL_REVIEW = 'true'
$env:API_BASE_URL = 'http://127.0.0.1:8020'
& node web/node_modules/next/dist/bin/next build --webpack $runtimePath
if ($LASTEXITCODE -ne 0) { throw 'Review build failed.' }
