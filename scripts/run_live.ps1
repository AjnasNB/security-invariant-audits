param(
    [ValidateSet('connection','single','pilot','application','text')]
    [string]$Mode = 'connection',
    [string]$Batch = '',
    [string]$DeltaRoot = 'D:\delta voice\my harness',
    [string]$Task = 'access_helper',
    [string]$Condition = 'original',
    [string]$Queries = ''
)
$ErrorActionPreference = 'Stop'
$researchRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $researchRoot
$researchTsx = Join-Path $DeltaRoot 'node_modules\.bin\tsx.cmd'
if (-not (Test-Path -LiteralPath $researchTsx)) {
    throw 'Delta tsx runner is unavailable. Configure DeltaRoot without substituting another model.'
}
$researchArguments = @(
    (Join-Path $researchRoot 'runner\study.ts'),
    "--mode=$Mode", "--delta-root=$DeltaRoot", "--task=$Task", "--condition=$Condition"
)
if ($Batch) { $researchArguments += "--batch=$Batch" }
if ($Queries) { $researchArguments += "--queries=$Queries" }
Write-Output 'This command makes paid Azure GPT-6.1 Sol requests with the documented research caps.'
& $researchTsx @researchArguments
if ($LASTEXITCODE -ne 0) { throw 'Live run stopped; inspect preserved batch evidence before retrying.' }
