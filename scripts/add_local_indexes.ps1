[CmdletBinding()]
param(
    [string]$DataDir = "",

    [int]$Limit = 0,

    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$entrypoint = Join-Path $projectRoot "scripts\add_local_indexes.py"

if (-not (Test-Path -LiteralPath $entrypoint)) {
    throw "Entrypoint not found: $entrypoint"
}

$arguments = @($entrypoint)

if ($DataDir) {
    $arguments += @("--data-dir", $DataDir)
}

if ($Limit -gt 0) {
    $arguments += @("--limit", $Limit)
}

if ($DryRun) {
    $arguments += "--dry-run"
}

Write-Host "[add-local-indexes] data dir: $DataDir"
Write-Host "[add-local-indexes] dry run: $($DryRun.IsPresent)"

& python @arguments
exit $LASTEXITCODE
