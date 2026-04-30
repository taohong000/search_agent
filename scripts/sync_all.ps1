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

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

$syncMarkdown = Join-Path $scriptRoot "sync_reviewed_markdown.ps1"
$addIndexes = Join-Path $scriptRoot "add_local_indexes.ps1"
$buildVersions = Join-Path $scriptRoot "build_version_indexes.ps1"

foreach ($script in @($syncMarkdown, $addIndexes, $buildVersions)) {
    if (-not (Test-Path -LiteralPath $script)) {
        throw "Required script not found: $script"
    }
}

$syncArgs = @{
    EnvFile = $EnvFile
    CrawlerRoot = $CrawlerRoot
    CrawlerOutputDir = $CrawlerOutputDir
    Statuses = $Statuses
}

$localIndexArgs = @{}

$versionArgs = @{
    EnvFile = $EnvFile
    Statuses = $Statuses
}

if ($DataDir) {
    $syncArgs.DataDir = $DataDir
    $localIndexArgs.DataDir = $DataDir
    $versionArgs.DataDir = $DataDir
}

if ($SinceUpdatedAt) {
    $syncArgs.SinceUpdatedAt = $SinceUpdatedAt
}

if ($SourceId -gt 0) {
    $syncArgs.SourceId = $SourceId
    $versionArgs.SourceId = $SourceId
}

if ($Limit -gt 0) {
    $syncArgs.Limit = $Limit
    $localIndexArgs.Limit = $Limit
}

if ($DryRun) {
    $syncArgs.DryRun = $true
    $localIndexArgs.DryRun = $true
    $versionArgs.DryRun = $true
}

Write-Host "[sync-all] step 1/3: sync reviewed markdown"
& $syncMarkdown @syncArgs
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "[sync-all] step 2/3: add local indexes"
& $addIndexes @localIndexArgs
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "[sync-all] step 3/3: build version indexes"
& $buildVersions @versionArgs
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
