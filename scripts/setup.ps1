$ErrorActionPreference = 'Stop'
$researchRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $researchRoot
$researchDrive = $researchRoot.Substring(0, 1).ToLowerInvariant()
$researchLinuxRoot = '/mnt/' + $researchDrive + '/' + $researchRoot.Substring(3).Replace('\', '/')
wsl -d Ubuntu -- docker build -t ajnas-security-study:20261001 "$researchLinuxRoot/sandbox"
if ($LASTEXITCODE -ne 0) { throw 'Container build failed.' }
wsl -d Ubuntu -- docker build -f "$researchLinuxRoot/sandbox/Dockerfile.app" -t ajnas-security-app:20261001 "$researchLinuxRoot/sandbox"
if ($LASTEXITCODE -ne 0) { throw 'Application container build failed.' }
wsl -d Ubuntu -- docker build -f "$researchLinuxRoot/sandbox/Dockerfile.tenant" -t ajnas-security-tenant:20261001 "$researchLinuxRoot/sandbox"
if ($LASTEXITCODE -ne 0) { throw 'Tenant-library container build failed.' }
python -m research.sandbox
if ($LASTEXITCODE -ne 0) { throw 'Isolation checks failed.' }
python -c 'from research.sandbox import probe, APP_IMAGE; probe(APP_IMAGE)'
if ($LASTEXITCODE -ne 0) { throw 'Application isolation checks failed.' }
