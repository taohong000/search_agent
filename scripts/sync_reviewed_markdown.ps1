[CmdletBinding()]
param(
    [string]$EnvFile = "D:\code\sicrawl\.env.qa",

    [string]$CrawlerRoot = "D:\code\sicrawl",

    [string]$CrawlerOutputDir = "D:\code\sicrawl\output",

    [string]$DataDir = "",

    [string]$Statuses = "auto_approved,manual_approved,filter_disabled",

    [string]$SinceUpdatedAt = "",

    [int]$SourceId = 0,

    [int]$Limit = 0,

    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$entrypoint = Join-Path $projectRoot "scripts\sync_reviewed_markdown.py"

if (-not (Test-Path -LiteralPath $entrypoint)) {
    throw "Entrypoint not found: $entrypoint"
}

$python = "python"
$arguments = @(
    $entrypoint,
    "--env-file", $EnvFile,
    "--crawler-root", $CrawlerRoot,
    "--crawler-output-dir", $CrawlerOutputDir,
    "--statuses", $Statuses
)

if ($DataDir) {
    $arguments += @("--data-dir", $DataDir)
}

if ($SinceUpdatedAt) {
    $arguments += @("--since-updated-at", $SinceUpdatedAt)
}

if ($SourceId -gt 0) {
    $arguments += @("--source-id", $SourceId)
}

if ($Limit -gt 0) {
    $arguments += @("--limit", $Limit)
}

if ($DryRun) {
    $arguments += "--dry-run"
}

Write-Host "[sync-reviewed-markdown] env file: $EnvFile"
Write-Host "[sync-reviewed-markdown] crawler output dir: $CrawlerOutputDir"
Write-Host "[sync-reviewed-markdown] statuses: $Statuses"
Write-Host "[sync-reviewed-markdown] source id: $SourceId"
Write-Host "[sync-reviewed-markdown] dry run: $($DryRun.IsPresent)"

& $python @arguments
exit $LASTEXITCODE
