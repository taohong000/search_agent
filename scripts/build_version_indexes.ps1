[CmdletBinding()]
param(
    [string]$EnvFile = "D:\code\sicrawl\.env.qa",

    [string]$DataDir = "",

    [int]$SourceId = 0,

    [string]$Statuses = "auto_approved,manual_approved,filter_disabled",

    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$entrypoint = Join-Path $projectRoot "scripts\build_version_indexes.py"

if (-not (Test-Path -LiteralPath $entrypoint)) {
    throw "Entrypoint not found: $entrypoint"
}

$arguments = @(
    $entrypoint,
    "--env-file", $EnvFile,
    "--statuses", $Statuses
)

if ($DataDir) {
    $arguments += @("--data-dir", $DataDir)
}

if ($SourceId -gt 0) {
    $arguments += @("--source-id", $SourceId)
}

if ($DryRun) {
    $arguments += "--dry-run"
}

Write-Host "[build-version-indexes] env file: $EnvFile"
Write-Host "[build-version-indexes] data dir: $DataDir"
Write-Host "[build-version-indexes] source id: $SourceId"
Write-Host "[build-version-indexes] statuses: $Statuses"
Write-Host "[build-version-indexes] dry run: $($DryRun.IsPresent)"

& python @arguments
exit $LASTEXITCODE
