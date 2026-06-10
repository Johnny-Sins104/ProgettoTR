[CmdletBinding()]
param(
    [int]$RefreshSeconds = 3,
    [switch]$Once
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "SilentlyContinue"

$AutomationDir = $PSScriptRoot
$ProjectRoot = Split-Path -Parent $AutomationDir
$StatePath = Join-Path $AutomationDir "state.json"
$QuotaPath = Join-Path $AutomationDir "quota.json"
$RoadmapPath = Join-Path $AutomationDir "roadmap.json"
$LogsDir = Join-Path $AutomationDir "logs"
$ReviewPath = Join-Path $AutomationDir "CODEX_REVIEW.md"

function Read-JsonFile([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
}

function Format-ClaudeEvents([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        return @("Output live non disponibile per questo ciclo.")
    }

    $result = @()
    foreach ($line in @(Get-Content -LiteralPath $Path -Tail 80)) {
        try {
            $event = $line | ConvertFrom-Json
            if ($event.type -eq "assistant" -and $null -ne $event.message.content) {
                foreach ($content in $event.message.content) {
                    if ($content.type -eq "text" -and $content.text) {
                        $result += "Claude: " + (($content.text -replace "\s+", " ").Trim())
                    }
                    elseif ($content.type -eq "tool_use") {
                        $result += "Claude tool: $($content.name)"
                    }
                }
            }
            elseif ($event.type -eq "result") {
                $result += "Claude result: subtype=$($event.subtype)"
            }
        }
        catch {
            if (-not [string]::IsNullOrWhiteSpace($line)) {
                $result += $line
            }
        }
    }
    return @($result | Select-Object -Last 12)
}

do {
    Clear-Host
    $state = Read-JsonFile $StatePath
    $quota = Read-JsonFile $QuotaPath
    $roadmap = Read-JsonFile $RoadmapPath
    $claudeProcess = @(Get-CimInstance Win32_Process -Filter "Name = 'claude.exe'")
    $latestClaudeLog = Get-ChildItem -LiteralPath $LogsDir -Filter "CLAUDE_*.json" |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    $latestCodexLog = Get-ChildItem -LiteralPath $LogsDir -Filter "CODEX_CYCLE_*.jsonl" |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1

    Write-Host "ProgettoTR - Claude/Codex live monitor"
    Write-Host ("time={0:yyyy-MM-dd HH:mm:ss}" -f (Get-Date))
    Write-Host ""
    Write-Host "status=$($state.status) cycle=$($state.cycle)/$($state.max_cycles)"
    Write-Host "current_patch=$($state.current_patch_id)"
    $nextPatch = @($roadmap.items | Where-Object { $_.status -eq "pending" -and [bool]$_.auto_run }) | Select-Object -First 1
    if ($null -ne $nextPatch) {
        Write-Host "next_pending_patch=$($nextPatch.id)"
    }
    Write-Host "last_action=$($state.last_action)"
    Write-Host "claude_processes=$($claudeProcess.Count)"
    Write-Host "quota_active=$($quota.active) triggered_by=$($quota.triggered_by)"
    if ([bool]$quota.active) {
        Write-Host "claude_reset=$($quota.claude_reset_at)"
        Write-Host "codex_reset=$($quota.codex_reset_at)"
    }

    Write-Host ""
    Write-Host "Ultimi file progetto modificati:"
    Get-ChildItem -LiteralPath $ProjectRoot -Recurse -File |
        Where-Object {
            $_.FullName -notlike "$AutomationDir*" -and
            $_.FullName -notlike "$(Join-Path $ProjectRoot '.git')*" -and
            $_.FullName -notmatch "\\(__pycache__|\.pytest_cache)\\"
        } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 8 |
        ForEach-Object { Write-Host ("{0:HH:mm:ss} {1}" -f $_.LastWriteTime, $_.FullName.Substring($ProjectRoot.Length + 1)) }

    Write-Host ""
    Write-Host "Attivita Claude:"
    if ($null -ne $latestClaudeLog) {
        Write-Host "log=$($latestClaudeLog.Name)"
        Format-ClaudeEvents $latestClaudeLog.FullName | ForEach-Object { Write-Host $_ }
    }
    else {
        Write-Host "Il ciclo corrente usa ancora output finale; osserva processo e file modificati."
    }

    Write-Host ""
    Write-Host "Attivita Codex:"
    if ($state.status -eq "codex_review_running" -and $null -ne $latestCodexLog) {
        Write-Host "log=$($latestCodexLog.Name)"
        Get-Content -LiteralPath $latestCodexLog.FullName -Tail 12 | ForEach-Object { Write-Host $_ }
    }
    elseif ($state.status -eq "codex_review_running") {
        Write-Host "Review Codex in esecuzione; il report apparira qui."
    }
    elseif (Test-Path -LiteralPath $ReviewPath) {
        Write-Host "Codex non sta revisionando. Ultima review disponibile in automation\CODEX_REVIEW.md."
    }
    else {
        Write-Host "Codex non sta revisionando."
    }

    if ($Once) { break }
    Start-Sleep -Seconds ([Math]::Max(1, $RefreshSeconds))
} while ($true)
