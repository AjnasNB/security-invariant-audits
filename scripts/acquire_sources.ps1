param([switch]$IncludeERP)
$ErrorActionPreference = 'Stop'
$researchRoot = Split-Path -Parent $PSScriptRoot
$researchSources = Join-Path $researchRoot '_sources'
New-Item -ItemType Directory -Path $researchSources -Force | Out-Null
$researchRepositories = @{
    mucoco = 'https://github.com/mucoco-tester/mucoco-tester.github.io.git'
    jailguard = 'https://github.com/shiningrain/JailGuard.git'
    humaneval = 'https://github.com/openai/human-eval.git'
    django_multitenant = 'https://github.com/citusdata/django-multitenant.git'
    agentdojo = 'https://github.com/ethz-spylab/agentdojo.git'
    fastapi_app = 'https://github.com/fastapi/full-stack-fastapi-template.git'
    erpnext = 'https://github.com/frappe/erpnext.git'
}
$researchManifest = Get-Content -LiteralPath (Join-Path $researchRoot 'datasets\sources.json') -Raw | ConvertFrom-Json
foreach ($researchSource in $researchManifest.sources) {
    $researchTarget = Join-Path $researchSources $researchSource.id
    if (Test-Path -LiteralPath $researchTarget) {
        $researchCurrent = git -C $researchTarget rev-parse HEAD
        if ($researchCurrent -ne $researchSource.commit) {
            throw "Existing checkout $researchTarget is at a different commit; preserve it and resolve explicitly."
        }
        continue
    }
    git clone --filter=blob:none --no-checkout $researchRepositories[$researchSource.id] $researchTarget
    if ($LASTEXITCODE -ne 0) { throw "Clone failed for $($researchSource.id)" }
    git -C $researchTarget checkout --detach $researchSource.commit
    if ($LASTEXITCODE -ne 0) { throw "Pinned checkout failed for $($researchSource.id)" }
}
Write-Output 'Pinned source checkouts acquired. No remote writes or branches created.'
