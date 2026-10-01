$ErrorActionPreference = 'Stop'
$researchRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $researchRoot
$env:PYTHONDONTWRITEBYTECODE = '1'
python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Research unit tests failed.' }
python -m research.validate
if ($LASTEXITCODE -ne 0) { throw 'Independent evaluator validation failed.' }
python -m research.tenant
if ($LASTEXITCODE -ne 0) { throw 'Tenant-library integration failed.' }
python -m research.dojo
if ($LASTEXITCODE -ne 0) { throw 'AgentDojo author-code smoke failed.' }
python -m research.audit
if ($LASTEXITCODE -ne 0) { throw 'Environment recording failed.' }
Write-Output 'Offline checks complete. No live inference or remote writes.'
