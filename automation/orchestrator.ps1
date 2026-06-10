[CmdletBinding()]
param(
    [switch]$Approve,
    [switch]$Status,
    [switch]$Stop,
    [switch]$Once,
    [switch]$Validate,
    [switch]$RoadmapPreview,
    [switch]$QuotaStatus,
    [ValidateSet("claude", "codex")]
    [string]$QuotaLimited,
    [string]$ClaudeResetAt,
    [string]$CodexResetAt
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$AutomationDir = $PSScriptRoot
$ProjectRoot = Split-Path -Parent $AutomationDir
$ConfigPath = Join-Path $AutomationDir "config.json"
$StatePath = Join-Path $AutomationDir "state.json"
$QuotaPath = Join-Path $AutomationDir "quota.json"
$PromptPath = Join-Path $AutomationDir "NEXT_CLAUDE_PROMPT.md"
$ApprovalPath = Join-Path $AutomationDir "APPROVE_CLAUDE"
$StopPath = Join-Path $AutomationDir "STOP"
$DonePath = Join-Path $AutomationDir "CLAUDE_DONE.json"
$CodexInstructionsPath = Join-Path $AutomationDir "CODEX_REVIEW_INSTRUCTIONS.md"
$CodexSchemaPath = Join-Path $AutomationDir "codex_review_schema.json"
$RoadmapPath = Join-Path $AutomationDir "roadmap.json"
$HistoryDir = Join-Path $AutomationDir "history"
$LogsDir = Join-Path $AutomationDir "logs"
$ClaudeSafetyPrompt = @"
You are running inside an automated patch/review loop.
Do not start trading bots, use private exchange endpoints or credentials, send Telegram messages, delete files, reset Git, commit, push, or modify automation/. Public historical market-data retrieval is allowed only when the canonical patch explicitly requires it.
Work only on the requested patch. Run relevant tests and leave a precise report.
"@

function Read-JsonFile {
    param([Parameter(Mandatory)][string]$Path)
    return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
}

function Write-JsonAtomic {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)]$Value
    )

    $tempPath = "$Path.tmp"
    $json = $Value | ConvertTo-Json -Depth 10
    [System.IO.File]::WriteAllText($tempPath, $json, [System.Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $tempPath -Destination $Path -Force
}

function Write-ProjectSnapshot {
    param([Parameter(Mandatory)][string]$Path)

    $snapshot = [ordered]@{}
    $files = @(git ls-files --cached --others --exclude-standard)
    foreach ($relativePath in ($files | Sort-Object -Unique)) {
        $normalizedPath = $relativePath.Replace("\", "/")
        if ($normalizedPath.StartsWith("automation/")) {
            continue
        }

        $fullPath = Join-Path $ProjectRoot $relativePath
        if (Test-Path -LiteralPath $fullPath -PathType Leaf) {
            $item = Get-Item -LiteralPath $fullPath
            $snapshot[$normalizedPath] = [ordered]@{
                sha256 = (Get-FileHash -LiteralPath $fullPath -Algorithm SHA256).Hash
                length = [long]$item.Length
            }
        }
    }

    Write-JsonAtomic -Path $Path -Value $snapshot
}

function Write-SnapshotDiff {
    param(
        [Parameter(Mandatory)][string]$BeforePath,
        [Parameter(Mandatory)][string]$AfterPath,
        [Parameter(Mandatory)][string]$OutputPath
    )

    $beforeObject = Read-JsonFile -Path $BeforePath
    $afterObject = Read-JsonFile -Path $AfterPath
    $before = @{}
    $after = @{}
    foreach ($property in $beforeObject.PSObject.Properties) {
        $before[$property.Name] = $property.Value
    }
    foreach ($property in $afterObject.PSObject.Properties) {
        $after[$property.Name] = $property.Value
    }

    $changes = @()
    $paths = @($before.Keys + $after.Keys | Sort-Object -Unique)
    foreach ($path in $paths) {
        if (-not $before.ContainsKey($path)) {
            $changes += [ordered]@{ path = $path; change = "added" }
        }
        elseif (-not $after.ContainsKey($path)) {
            $changes += [ordered]@{ path = $path; change = "deleted" }
        }
        elseif ($before[$path].sha256 -ne $after[$path].sha256) {
            $changes += [ordered]@{ path = $path; change = "modified" }
        }
    }

    $result = [ordered]@{
        schema_version = 1
        changed_count = $changes.Count
        files = $changes
    }
    Write-JsonAtomic -Path $OutputPath -Value $result
}

function Convert-ToUtcTimestamp {
    param(
        [string]$Value,
        [Parameter(Mandatory)][datetimeoffset]$Fallback
    )

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $Fallback.ToUniversalTime().ToString("o")
    }
    return ([datetimeoffset]::Parse($Value)).ToUniversalTime().ToString("o")
}

function Start-QuotaBarrier {
    param(
        [Parameter(Mandatory)][string]$Actor,
        [Parameter(Mandatory)][string]$Reason,
        [Parameter(Mandatory)][string]$ResumeStatus,
        [string]$ClaudeReset,
        [string]$CodexReset
    )

    $config = Read-JsonFile -Path $ConfigPath
    $quota = Read-JsonFile -Path $QuotaPath
    $state = Read-JsonFile -Path $StatePath
    $fallback = [datetimeoffset]::UtcNow.AddHours([double]$config.quota_default_cooldown_hours)
    $wasActive = [bool]$quota.active
    if ($ResumeStatus -eq "quota_waiting" -and -not [string]::IsNullOrWhiteSpace([string]$quota.resume_status)) {
        $ResumeStatus = [string]$quota.resume_status
    }

    $quota.active = $true
    $quota.triggered_by = $Actor
    $quota.reason = $Reason
    $quota.entered_at = [datetimeoffset]::UtcNow.ToString("o")
    $quota.resume_status = $ResumeStatus
    if ([string]::IsNullOrWhiteSpace($ClaudeReset) -and $wasActive -and
        -not [string]::IsNullOrWhiteSpace([string]$quota.claude_reset_at)) {
        $quota.claude_reset_at = [string]$quota.claude_reset_at
    }
    else {
        $quota.claude_reset_at = Convert-ToUtcTimestamp -Value $ClaudeReset -Fallback $fallback
    }
    if ([string]::IsNullOrWhiteSpace($CodexReset) -and $wasActive -and
        -not [string]::IsNullOrWhiteSpace([string]$quota.codex_reset_at)) {
        $quota.codex_reset_at = [string]$quota.codex_reset_at
    }
    else {
        $quota.codex_reset_at = Convert-ToUtcTimestamp -Value $CodexReset -Fallback $fallback
    }
    Write-JsonAtomic -Path $QuotaPath -Value $quota

    $state.status = "quota_waiting"
    $state.last_action = "Quota barrier triggered by $Actor; waiting for both resets"
    $state.updated_at = [datetimeoffset]::UtcNow.ToString("o")
    Write-JsonAtomic -Path $StatePath -Value $state
}

function Test-AndResumeQuotaBarrier {
    $quota = Read-JsonFile -Path $QuotaPath
    if (-not [bool]$quota.active) {
        return $false
    }

    if ([string]::IsNullOrWhiteSpace([string]$quota.claude_reset_at) -or
        [string]::IsNullOrWhiteSpace([string]$quota.codex_reset_at)) {
        return $true
    }

    $now = [datetimeoffset]::UtcNow
    $claudeReady = $now -ge [datetimeoffset]::Parse([string]$quota.claude_reset_at)
    $codexReady = $now -ge [datetimeoffset]::Parse([string]$quota.codex_reset_at)
    if (-not ($claudeReady -and $codexReady)) {
        return $true
    }

    $state = Read-JsonFile -Path $StatePath
    $state.status = [string]$quota.resume_status
    $state.last_action = "Both quota windows reset; resuming $($quota.resume_status)"
    $state.updated_at = $now.ToString("o")
    Write-JsonAtomic -Path $StatePath -Value $state

    $quota.active = $false
    $quota.reason = $null
    $quota.resume_status = $null
    Write-JsonAtomic -Path $QuotaPath -Value $quota
    return $false
}

function Show-Quota {
    $quota = Read-JsonFile -Path $QuotaPath
    Write-Host "quota_active=$($quota.active) triggered_by=$($quota.triggered_by)"
    Write-Host "resume_status=$($quota.resume_status)"
    Write-Host "claude_reset_at=$($quota.claude_reset_at)"
    Write-Host "codex_reset_at=$($quota.codex_reset_at)"
    Write-Host "reason=$($quota.reason)"
}

function Test-ClaudeQuotaFailure {
    param(
        [Parameter(Mandatory)][string]$LogPath,
        [ValidateSet("claude", "codex")]
        [string]$Actor = "claude"
    )

    $config = Read-JsonFile -Path $ConfigPath
    $text = Get-Content -LiteralPath $LogPath -Raw
    $patterns = $config.quota_error_patterns
    if ($Actor -eq "codex") {
        $patterns = $config.codex_quota_error_patterns
    }
    foreach ($pattern in $patterns) {
        if ($text.IndexOf([string]$pattern, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
            return $true
        }
    }
    return $false
}

function Get-ClaudeSessionId {
    param([Parameter(Mandatory)][string]$LogPath)

    $text = Get-Content -LiteralPath $LogPath -Raw
    try {
        $result = $text | ConvertFrom-Json
        if ($null -ne $result.session_id) {
            return [string]$result.session_id
        }
    }
    catch {
        $match = [regex]::Match($text, '"session_id"\s*:\s*"([^"]+)"')
        if ($match.Success) {
            return $match.Groups[1].Value
        }
    }
    return $null
}

function Get-CodexCommand {
    $candidates = @(
        Get-ChildItem -Path (Join-Path $env:LOCALAPPDATA "OpenAI\Codex\bin") -Filter "codex.exe" -Recurse -File -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending
    )
    if ($candidates.Count -eq 0) {
        return $null
    }
    return $candidates[0].FullName
}

function Get-CodexSessionId {
    param([Parameter(Mandatory)][string]$LogPath)

    $text = Get-Content -LiteralPath $LogPath -Raw
    $match = [regex]::Match($text, '"thread_id"\s*:\s*"([^"]+)"')
    if ($match.Success) {
        return $match.Groups[1].Value
    }
    return $null
}

function Write-TextFile {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Text
    )
    [System.IO.File]::WriteAllText($Path, $Text, [System.Text.UTF8Encoding]::new($false))
}

function Test-Roadmap {
    $roadmap = Read-JsonFile -Path $RoadmapPath
    if ([string]::IsNullOrWhiteSpace([string]$roadmap.source)) {
        throw "Roadmap source is missing"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot ([string]$roadmap.source)))) {
        throw "Roadmap source does not exist: $($roadmap.source)"
    }

    $items = @($roadmap.items)
    if ($items.Count -eq 0) {
        throw "Roadmap has no items"
    }

    $ids = @($items | ForEach-Object { [string]$_.id })
    if (@($ids | Where-Object { [string]::IsNullOrWhiteSpace($_) }).Count -gt 0) {
        throw "Every roadmap item must have an id"
    }
    if (@($ids | Group-Object | Where-Object { $_.Count -gt 1 }).Count -gt 0) {
        throw "Roadmap item ids must be unique"
    }

    $allowedStatuses = @("completed", "in_progress", "pending", "optional")
    foreach ($item in $items) {
        if ([string]$item.status -notin $allowedStatuses) {
            throw "Roadmap item $($item.id) has invalid status: $($item.status)"
        }
        foreach ($prerequisite in @($item.prerequisites)) {
            if ([string]$prerequisite -notin $ids) {
                throw "Roadmap item $($item.id) references unknown prerequisite: $prerequisite"
            }
        }
        if ([bool]$item.auto_run -and [string]$item.status -ne "completed") {
            $itemSource = [string]$roadmap.source
            if ($null -ne $item.PSObject.Properties["source_document"] -and
                -not [string]::IsNullOrWhiteSpace([string]$item.source_document)) {
                $itemSource = [string]$item.source_document
            }
            if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot $itemSource))) {
                throw "Automatic roadmap item $($item.id) source does not exist: $itemSource"
            }
            if ([string]::IsNullOrWhiteSpace([string]$item.source_reference) -or
                @($item.scope).Count -eq 0 -or @($item.required_tests).Count -eq 0 -or
                @($item.constraints).Count -eq 0 -or
                [string]::IsNullOrWhiteSpace([string]$item.report)) {
                throw "Automatic roadmap item $($item.id) lacks an explicit specification"
            }
        }
    }
    if (@($items | Where-Object { $_.status -eq "in_progress" }).Count -gt 1) {
        throw "Roadmap cannot have more than one in-progress item"
    }
    return $roadmap
}

function Show-RoadmapPreview {
    $roadmap = Test-Roadmap
    $state = Read-JsonFile -Path $StatePath
    $completed = @($roadmap.items | Where-Object { $_.status -eq "completed" } | ForEach-Object { [string]$_.id })
    if ($state.status -eq "approved" -and [string]$state.current_patch_id -notin $completed) {
        $completed += [string]$state.current_patch_id
    }
    $eligible = @(
        $roadmap.items | Where-Object {
            $_.status -eq "pending" -and
            [bool]$_.auto_run -and
            @($_.prerequisites | Where-Object { $_ -notin $completed }).Count -eq 0
        }
    ) | Select-Object -First 1

    Write-Host "current_patch=$($state.current_patch_id) status=$($state.status)"
    if ($null -eq $eligible) {
        Write-Host "next_patch=NONE"
    }
    else {
        $itemSource = [string]$roadmap.source
        if ($null -ne $eligible.PSObject.Properties["source_document"] -and
            -not [string]::IsNullOrWhiteSpace([string]$eligible.source_document)) {
            $itemSource = [string]$eligible.source_document
        }
        Write-Host "next_patch=$($eligible.id) title=$($eligible.title)"
        Write-Host "source=$itemSource"
        Write-Host "reference=$($eligible.source_reference)"
    }
}

function Start-NextRoadmapPatch {
    $config = Read-JsonFile -Path $ConfigPath
    $state = Read-JsonFile -Path $StatePath
    $roadmap = Test-Roadmap

    if (-not [string]::IsNullOrWhiteSpace([string]$state.current_patch_id)) {
        $current = @($roadmap.items | Where-Object { $_.id -eq $state.current_patch_id }) | Select-Object -First 1
        if ($null -ne $current -and $current.status -eq "in_progress") {
            $current.status = "completed"
        }
    }

    $completed = @($roadmap.items | Where-Object { $_.status -eq "completed" } | ForEach-Object { [string]$_.id })
    $eligible = @(
        $roadmap.items | Where-Object {
            $_.status -eq "pending" -and
            [bool]$_.auto_run -and
            @($_.prerequisites | Where-Object { $_ -notin $completed }).Count -eq 0
        }
    ) | Select-Object -First 1

    if ($null -eq $eligible) {
        $remainingAuto = @($roadmap.items | Where-Object { $_.status -eq "pending" -and [bool]$_.auto_run })
        Write-JsonAtomic -Path $RoadmapPath -Value $roadmap
        if ($remainingAuto.Count -eq 0) {
            Update-State -NewStatus "roadmap_complete" -Message "All approved automatic roadmap items completed; optional items were not started" | Out-Null
        }
        else {
            Update-State -NewStatus "roadmap_blocked" -Message "No eligible approved roadmap item; prerequisites or specification missing" | Out-Null
        }
        return
    }

    $itemSource = [string]$roadmap.source
    if ($null -ne $eligible.PSObject.Properties["source_document"] -and
        -not [string]::IsNullOrWhiteSpace([string]$eligible.source_document)) {
        $itemSource = [string]$eligible.source_document
    }
    $sourcePath = Join-Path $ProjectRoot $itemSource
    if (-not (Test-Path -LiteralPath $sourcePath)) {
        Update-State -NewStatus "roadmap_blocked" -Message "Canonical roadmap source missing: $itemSource" | Out-Null
        return
    }
    if ([string]::IsNullOrWhiteSpace([string]$eligible.source_reference) -or
        @($eligible.scope).Count -eq 0 -or @($eligible.required_tests).Count -eq 0) {
        Update-State -NewStatus "roadmap_blocked" -Message "Roadmap item $($eligible.id) lacks an explicit specification" | Out-Null
        return
    }

    $scopeText = (@($eligible.scope) | ForEach-Object { "- $_" }) -join "`n"
    $testsText = (@($eligible.required_tests) | ForEach-Object { "- $_" }) -join "`n"
    $constraintsText = (@($eligible.constraints) | ForEach-Object { "- $_" }) -join "`n"
    $prompt = @"
# $($eligible.id) - $($eligible.title)

Implementa esclusivamente questa patch canonica gia approvata nella roadmap.

Fonte obbligatoria:
- $itemSource
- riferimento: $($eligible.source_reference)

Scope:
$scopeText

Test obbligatori:
$testsText

Vincoli:
$constraintsText

Regole operative:
- non inventare requisiti, patch successive o scope aggiuntivo;
- se la fonte e insufficiente o contraddittoria, fermati e dichiaralo nel report;
- leggi e modifica soltanto i file necessari;
- esegui prima test mirati e poi `python -m pytest -q` una sola volta se i mirati passano;
- non avviare bot, non usare API private, endpoint ordini o Telegram, non fare commit o push;
- non modificare automation/.

Crea il report $($eligible.report) e fermati al termine della patch.
"@

    Write-TextFile -Path $PromptPath -Text $prompt
    $eligible.status = "in_progress"
    Write-JsonAtomic -Path $RoadmapPath -Value $roadmap

    $state.current_patch_id = [string]$eligible.id
    $state.cycle = 0
    $state.max_cycles = [int]$config.max_cycles
    $state.active_claude_session_id = $null
    $state.active_codex_session_id = $null
    $state.active_prompt_archive = $null
    $state.status = "awaiting_claude"
    $state.last_action = "Canonical roadmap advanced to $($eligible.id)"
    $state.updated_at = [datetimeoffset]::UtcNow.ToString("o")
    Write-JsonAtomic -Path $StatePath -Value $state
}

function Invoke-DirectCodexReview {
    param([switch]$Resume)

    $config = Read-JsonFile -Path $ConfigPath
    $state = Read-JsonFile -Path $StatePath
    $codex = Get-CodexCommand
    if ([string]::IsNullOrWhiteSpace($codex)) {
        Update-State -NewStatus "awaiting_codex_review" -Message "Direct Codex CLI unavailable; waiting for fallback heartbeat" | Out-Null
        return
    }

    $cycleLabel = "{0:D2}" -f [int]$state.cycle
    $codexLog = Join-Path $LogsDir "CODEX_CYCLE_$cycleLabel.jsonl"
    $codexResult = Join-Path $LogsDir "CODEX_RESULT_CYCLE_$cycleLabel.json"
    $reviewPath = Join-Path $AutomationDir "CODEX_REVIEW.md"
    $reviewArchive = Join-Path $HistoryDir "CODEX_REVIEW_CYCLE_$cycleLabel.md"

    Update-State -NewStatus "codex_review_running" -Message "Direct Codex review cycle $($state.cycle) started" | Out-Null

    if ($Resume -and -not [string]::IsNullOrWhiteSpace([string]$state.active_codex_session_id)) {
        $codexArgs = @(
            "-a", "never",
            "-s", [string]$config.codex_sandbox_mode,
            "-C", $ProjectRoot,
            "exec", "resume", [string]$state.active_codex_session_id,
            "--json",
            "--output-schema", $CodexSchemaPath,
            "-o", $codexResult,
            "Continue exactly from the interrupted independent review. Return the required structured decision."
        )
    }
    else {
        $instructions = Get-Content -LiteralPath $CodexInstructionsPath -Raw
        $prompt = "$instructions`n`nCurrent cycle: $($state.cycle)/$($state.max_cycles). Repository: $ProjectRoot"
        $codexArgs = @(
            "-a", "never",
            "-s", [string]$config.codex_sandbox_mode,
            "-C", $ProjectRoot,
            "-c", "model_reasoning_effort=`"$($config.codex_reasoning_effort)`"",
            "exec",
            "--json",
            "--output-schema", $CodexSchemaPath,
            "-o", $codexResult,
            $prompt
        )
    }

    $exitCode = -1
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        # Codex writes informational startup messages to stderr.
        $ErrorActionPreference = "Continue"
        & $codex @codexArgs 2>&1 | Tee-Object -FilePath $codexLog | Out-Null
        $exitCode = $LASTEXITCODE
    }
    catch {
        $_ | Out-String | Out-File -LiteralPath $codexLog -Encoding utf8
        $exitCode = 1
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    $state = Read-JsonFile -Path $StatePath
    $sessionId = Get-CodexSessionId -LogPath $codexLog
    if (-not [string]::IsNullOrWhiteSpace($sessionId)) {
        $state.active_codex_session_id = $sessionId
        Write-JsonAtomic -Path $StatePath -Value $state
    }

    # A completed structured decision takes precedence over quota text emitted
    # after the review. Enter the barrier only when no usable result exists.
    if ((Test-ClaudeQuotaFailure -LogPath $codexLog -Actor "codex") -and -not (Test-Path -LiteralPath $codexResult)) {
        Start-QuotaBarrier -Actor "codex" -Reason "Codex CLI quota limit detected" `
            -ResumeStatus "codex_resume" -ClaudeReset $ClaudeResetAt -CodexReset $CodexResetAt
        return
    }
    if ($exitCode -ne 0 -or -not (Test-Path -LiteralPath $codexResult)) {
        Update-State -NewStatus "blocked" -Message "Direct Codex review failed with exit code $exitCode" | Out-Null
        return
    }

    $result = Read-JsonFile -Path $codexResult
    Write-TextFile -Path $reviewPath -Text ([string]$result.review_markdown)
    Write-TextFile -Path $reviewArchive -Text ([string]$result.review_markdown)

    if ($result.decision -eq "approved") {
        Update-State -NewStatus "approved" -Message ([string]$result.summary) | Out-Null
    }
    elseif ($result.decision -eq "fix_required" -and [int]$state.cycle -lt [int]$state.max_cycles) {
        Write-TextFile -Path $PromptPath -Text ([string]$result.next_claude_prompt)
        Update-State -NewStatus "awaiting_claude" -Message ([string]$result.summary) | Out-Null
    }
    elseif ($result.decision -eq "blocked" -and
        [string]$result.review_markdown -match "sandbox|ambiente di esecuzione|environment") {
        $environmentRetries = 0
        if ($null -ne $state.PSObject.Properties["codex_environment_retries"]) {
            $environmentRetries = [int]$state.codex_environment_retries
        }
        if ($environmentRetries -lt [int]$config.codex_environment_retry_limit) {
            if ($null -eq $state.PSObject.Properties["codex_environment_retries"]) {
                $state | Add-Member -NotePropertyName codex_environment_retries -NotePropertyValue 0
            }
            $state.codex_environment_retries = $environmentRetries + 1
            $state.active_codex_session_id = $null
            $state.status = "awaiting_codex_review"
            $state.last_action = "Codex environment failure; retry $($state.codex_environment_retries)/$($config.codex_environment_retry_limit)"
            $state.updated_at = [datetimeoffset]::UtcNow.ToString("o")
            Write-JsonAtomic -Path $StatePath -Value $state
        }
        else {
            Update-State -NewStatus "blocked" -Message ([string]$result.summary) | Out-Null
        }
    }
    else {
        Update-State -NewStatus "blocked" -Message ([string]$result.summary) | Out-Null
    }
}

function Test-ExternalClaudeRunning {
    return @(
        Get-CimInstance Win32_Process -Filter "Name = 'claude.exe'" -ErrorAction SilentlyContinue
    ).Count -gt 0
}

function Update-State {
    param(
        [Parameter(Mandatory)][string]$NewStatus,
        [Parameter(Mandatory)][string]$Message
    )

    $state = Read-JsonFile -Path $StatePath
    $state.status = $NewStatus
    $state.last_action = $Message
    $state.updated_at = (Get-Date).ToUniversalTime().ToString("o")
    Write-JsonAtomic -Path $StatePath -Value $state
    return $state
}

function Show-State {
    $state = Read-JsonFile -Path $StatePath
    Write-Host ""
    Write-Host "Claude/Codex automation"
    Write-Host "status=$($state.status) cycle=$($state.cycle)/$($state.max_cycles)"
    Write-Host "last_action=$($state.last_action)"
    Write-Host "updated_at=$($state.updated_at)"
    Write-Host ""
}

function Test-Prerequisites {
    $config = Read-JsonFile -Path $ConfigPath
    $state = Read-JsonFile -Path $StatePath
    $claude = Get-Command $config.claude_command -ErrorAction SilentlyContinue
    if ($null -eq $claude) {
        throw "Claude Code CLI not found: $($config.claude_command)"
    }
    if ($state.status -in @("awaiting_claude_approval", "awaiting_claude") -and -not (Test-Path -LiteralPath $PromptPath)) {
        throw "Missing prompt: $PromptPath"
    }
    if ([int]$state.max_cycles -ne [int]$config.max_cycles) {
        throw "state.json and config.json disagree on max_cycles"
    }
    if ([bool]$config.direct_handoff_enabled -and [string]::IsNullOrWhiteSpace((Get-CodexCommand))) {
        throw "Direct Codex CLI not found under LOCALAPPDATA"
    }
    if ([bool]$config.auto_advance_roadmap -and -not (Test-Path -LiteralPath $RoadmapPath)) {
        throw "Canonical automation roadmap missing: $RoadmapPath"
    }
    if ([bool]$config.auto_advance_roadmap) {
        Test-Roadmap | Out-Null
    }

    $snapshotTestA = Join-Path $LogsDir "VALIDATION_SNAPSHOT_A.json"
    $snapshotTestB = Join-Path $LogsDir "VALIDATION_SNAPSHOT_B.json"
    $snapshotTestDiff = Join-Path $LogsDir "VALIDATION_SNAPSHOT_DIFF.json"
    Write-ProjectSnapshot -Path $snapshotTestA
    Copy-Item -LiteralPath $snapshotTestA -Destination $snapshotTestB -Force
    Write-SnapshotDiff -BeforePath $snapshotTestA -AfterPath $snapshotTestB -OutputPath $snapshotTestDiff
    $diff = Read-JsonFile -Path $snapshotTestDiff
    if ([int]$diff.changed_count -ne 0) {
        throw "Snapshot validation produced unexpected changes"
    }
    Remove-Item -LiteralPath $snapshotTestA, $snapshotTestB, $snapshotTestDiff -Force

    Write-Host "Validation OK"
    Write-Host "project=$ProjectRoot"
    Write-Host "claude=$($claude.Source)"
    Write-Host "prompt=$PromptPath"
    Write-Host "max_cycles=$($config.max_cycles)"
    Write-Host "approval_required=$($config.require_approval_before_claude)"
    Write-Host "direct_handoff=$($config.direct_handoff_enabled)"
    Write-Host "codex_sandbox=$($config.codex_sandbox_mode)"
    Write-Host "auto_advance_roadmap=$($config.auto_advance_roadmap)"
}

if (-not (Test-Path -LiteralPath $ConfigPath) -or -not (Test-Path -LiteralPath $StatePath) -or
    -not (Test-Path -LiteralPath $QuotaPath)) {
    throw "Automation config/state missing in $AutomationDir"
}

New-Item -ItemType Directory -Path $HistoryDir, $LogsDir -Force | Out-Null

if ($Status) {
    Show-State
    exit 0
}

if ($QuotaStatus) {
    Show-Quota
    exit 0
}

if ($Validate) {
    Test-Prerequisites
    exit 0
}

if ($RoadmapPreview) {
    Show-RoadmapPreview
    exit 0
}

if ($Approve) {
    [System.IO.File]::WriteAllText($ApprovalPath, (Get-Date).ToUniversalTime().ToString("o"))
    Write-Host "Claude execution approved for the next cycle."
}

if (-not [string]::IsNullOrWhiteSpace($QuotaLimited)) {
    $state = Read-JsonFile -Path $StatePath
    $resumeStatus = [string]$state.status
    if ($resumeStatus -eq "claude_running") {
        $resumeStatus = "claude_resume"
    }
    Start-QuotaBarrier -Actor $QuotaLimited -Reason "Quota limit recorded by operator" `
        -ResumeStatus $resumeStatus -ClaudeReset $ClaudeResetAt -CodexReset $CodexResetAt
    Show-Quota
    exit 0
}

if ($Stop) {
    [System.IO.File]::WriteAllText($StopPath, (Get-Date).ToUniversalTime().ToString("o"))
    Update-State -NewStatus "stopped" -Message "Stop requested by operator" | Out-Null
    Write-Host "Stop requested."
    exit 0
}

$mutex = [System.Threading.Mutex]::new($false, "Global\ProgettoTRClaudeCodexOrchestrator")
$ownsMutex = $false

try {
    $ownsMutex = $mutex.WaitOne(0)
    if (-not $ownsMutex) {
        if ($Approve) {
            Write-Host "Approval delivered to the running orchestrator."
            exit 0
        }
        throw "Another orchestrator instance is already running."
    }

    Set-Location -LiteralPath $ProjectRoot
    $config = Read-JsonFile -Path $ConfigPath
    $claude = Get-Command $config.claude_command -ErrorAction Stop

    while ($true) {
        if (Test-Path -LiteralPath $StopPath) {
            Update-State -NewStatus "stopped" -Message "STOP marker detected" | Out-Null
            Write-Host "STOP marker detected. Orchestrator stopped."
            break
        }

        $state = Read-JsonFile -Path $StatePath

        if (Test-AndResumeQuotaBarrier) {
            Write-Host "Waiting for both quota resets."
            Show-Quota
            if ($Once) {
                break
            }
            Start-Sleep -Seconds ([int]$config.poll_seconds)
            continue
        }
        $state = Read-JsonFile -Path $StatePath

        if ($state.status -eq "approved" -and [bool]$config.auto_advance_roadmap) {
            Start-NextRoadmapPatch
            continue
        }

        if ($state.status -in @("approved", "blocked", "stopped", "roadmap_complete", "roadmap_blocked")) {
            Show-State
            break
        }

        if ($state.status -eq "awaiting_claude_approval") {
            if (-not [bool]$config.require_approval_before_claude -or (Test-Path -LiteralPath $ApprovalPath)) {
                Update-State -NewStatus "awaiting_claude" -Message "Claude cycle approved" | Out-Null
                continue
            }

            Write-Host "Waiting for approval. Run: .\automation\orchestrator.ps1 -Approve"
        }
        elseif ($state.status -eq "awaiting_claude") {
            if (Test-ExternalClaudeRunning) {
                Write-Host "Waiting for the existing Claude Code process to exit."
                if ($Once) {
                    break
                }
                Start-Sleep -Seconds ([int]$config.poll_seconds)
                continue
            }
            if ([int]$state.cycle -ge [int]$config.max_cycles) {
                Update-State -NewStatus "blocked" -Message "Maximum Claude cycles reached" | Out-Null
                continue
            }
            if (-not (Test-Path -LiteralPath $PromptPath)) {
                Update-State -NewStatus "blocked" -Message "NEXT_CLAUDE_PROMPT.md is missing" | Out-Null
                continue
            }

            $state.cycle = [int]$state.cycle + 1
            $state.status = "claude_running"
            $state.last_action = "Claude Code cycle $($state.cycle) started"
            $state.updated_at = (Get-Date).ToUniversalTime().ToString("o")
            Write-JsonAtomic -Path $StatePath -Value $state

            $cycleLabel = "{0:D2}" -f [int]$state.cycle
            $promptArchive = Join-Path $HistoryDir "PROMPT_CYCLE_$cycleLabel.md"
            $claudeLog = Join-Path $LogsDir "CLAUDE_CYCLE_$cycleLabel.json"
            $beforeStatus = Join-Path $LogsDir "GIT_STATUS_BEFORE_CYCLE_$cycleLabel.txt"
            $afterStatus = Join-Path $LogsDir "GIT_STATUS_AFTER_CYCLE_$cycleLabel.txt"
            $beforeSnapshot = Join-Path $LogsDir "PROJECT_SNAPSHOT_BEFORE_CYCLE_$cycleLabel.json"
            $afterSnapshot = Join-Path $LogsDir "PROJECT_SNAPSHOT_AFTER_CYCLE_$cycleLabel.json"
            $changedFiles = Join-Path $LogsDir "CHANGED_FILES_CYCLE_$cycleLabel.json"
            $prompt = Get-Content -LiteralPath $PromptPath -Raw

            Copy-Item -LiteralPath $PromptPath -Destination $promptArchive -Force
            Remove-Item -LiteralPath $PromptPath -Force
            $state.active_prompt_archive = $promptArchive
            Write-JsonAtomic -Path $StatePath -Value $state
            git status --porcelain=v1 --untracked-files=all | Out-File -LiteralPath $beforeStatus -Encoding utf8
            Write-ProjectSnapshot -Path $beforeSnapshot

            $claudeArgs = @(
                "-p",
                "--output-format", [string]$config.claude_output_format,
                "--verbose",
                "--permission-mode", [string]$config.claude_permission_mode,
                "--effort", [string]$config.claude_effort,
                "--tools", [string]$config.claude_tools,
                "--append-system-prompt", $ClaudeSafetyPrompt,
                $prompt
            )

            $startedAt = (Get-Date).ToUniversalTime().ToString("o")
            $exitCode = -1
            try {
                & $claude.Source @claudeArgs 2>&1 | Tee-Object -FilePath $claudeLog | Out-Null
                $exitCode = $LASTEXITCODE
            }
            catch {
                $_ | Out-String | Out-File -LiteralPath $claudeLog -Encoding utf8
                $exitCode = 1
            }
            finally {
                git status --porcelain=v1 --untracked-files=all | Out-File -LiteralPath $afterStatus -Encoding utf8
                Write-ProjectSnapshot -Path $afterSnapshot
                Write-SnapshotDiff -BeforePath $beforeSnapshot -AfterPath $afterSnapshot -OutputPath $changedFiles
                Remove-Item -LiteralPath $ApprovalPath -Force -ErrorAction SilentlyContinue
            }

            $done = [ordered]@{
                schema_version = 1
                cycle = [int]$state.cycle
                exit_code = $exitCode
                started_at = $startedAt
                finished_at = (Get-Date).ToUniversalTime().ToString("o")
                prompt_archive = $promptArchive
                claude_log = $claudeLog
                git_status_before = $beforeStatus
                git_status_after = $afterStatus
                changed_files = $changedFiles
            }
            Write-JsonAtomic -Path $DonePath -Value $done

            $state = Read-JsonFile -Path $StatePath
            $state.active_claude_session_id = Get-ClaudeSessionId -LogPath $claudeLog
            Write-JsonAtomic -Path $StatePath -Value $state

            if (Test-ClaudeQuotaFailure -LogPath $claudeLog) {
                Start-QuotaBarrier -Actor "claude" -Reason "Claude Code quota limit detected" `
                    -ResumeStatus "claude_resume" -ClaudeReset $ClaudeResetAt -CodexReset $CodexResetAt
                Write-Host "Claude quota detected. Waiting for both quota resets."
            }
            elseif ($exitCode -eq 0) {
                Update-State -NewStatus "awaiting_codex_review" -Message "Claude cycle $($state.cycle) completed; waiting for independent Codex review" | Out-Null
                Write-Host "Claude cycle completed. Waiting for Codex heartbeat review."
            }
            else {
                Update-State -NewStatus "claude_failed" -Message "Claude cycle $($state.cycle) failed with exit code $exitCode" | Out-Null
                Write-Host "Claude failed with exit code $exitCode. Waiting for Codex heartbeat review."
            }
        }
        elseif ($state.status -eq "claude_resume") {
            if (Test-ExternalClaudeRunning) {
                Write-Host "Waiting for the existing Claude Code process to exit before resume."
                if ($Once) {
                    break
                }
                Start-Sleep -Seconds ([int]$config.poll_seconds)
                continue
            }
            $cycleLabel = "{0:D2}" -f [int]$state.cycle
            $resumeLog = Join-Path $LogsDir "CLAUDE_RESUME_CYCLE_$cycleLabel.json"
            $afterStatus = Join-Path $LogsDir "GIT_STATUS_AFTER_CYCLE_$cycleLabel.txt"
            $beforeSnapshot = Join-Path $LogsDir "PROJECT_SNAPSHOT_BEFORE_CYCLE_$cycleLabel.json"
            $afterSnapshot = Join-Path $LogsDir "PROJECT_SNAPSHOT_AFTER_CYCLE_$cycleLabel.json"
            $changedFiles = Join-Path $LogsDir "CHANGED_FILES_CYCLE_$cycleLabel.json"
            $resumePrompt = "Continue exactly from the interrupted task. Inspect current work, complete only the original archived prompt, run required tests, and produce the requested report."
            $claudeArgs = @("-p", "--output-format", [string]$config.claude_output_format, "--verbose",
                "--permission-mode", [string]$config.claude_permission_mode,
                "--effort", [string]$config.claude_effort, "--tools", [string]$config.claude_tools,
                "--append-system-prompt", $ClaudeSafetyPrompt)
            if (-not [string]::IsNullOrWhiteSpace([string]$state.active_claude_session_id)) {
                $claudeArgs += @("--resume", [string]$state.active_claude_session_id, $resumePrompt)
            }
            else {
                $originalPrompt = Get-Content -LiteralPath ([string]$state.active_prompt_archive) -Raw
                $claudeArgs += @("$resumePrompt`n`nOriginal task:`n$originalPrompt")
            }

            Update-State -NewStatus "claude_running" -Message "Resuming interrupted Claude cycle $($state.cycle)" | Out-Null
            $startedAt = [datetimeoffset]::UtcNow.ToString("o")
            $exitCode = -1
            try {
                & $claude.Source @claudeArgs 2>&1 | Tee-Object -FilePath $resumeLog | Out-Null
                $exitCode = $LASTEXITCODE
            }
            catch {
                $_ | Out-String | Out-File -LiteralPath $resumeLog -Encoding utf8
                $exitCode = 1
            }
            finally {
                git status --porcelain=v1 --untracked-files=all | Out-File -LiteralPath $afterStatus -Encoding utf8
                Write-ProjectSnapshot -Path $afterSnapshot
                Write-SnapshotDiff -BeforePath $beforeSnapshot -AfterPath $afterSnapshot -OutputPath $changedFiles
            }

            $state = Read-JsonFile -Path $StatePath
            $resumedSessionId = Get-ClaudeSessionId -LogPath $resumeLog
            if (-not [string]::IsNullOrWhiteSpace($resumedSessionId)) {
                $state.active_claude_session_id = $resumedSessionId
                Write-JsonAtomic -Path $StatePath -Value $state
            }
            $done = [ordered]@{
                schema_version = 1
                cycle = [int]$state.cycle
                exit_code = $exitCode
                started_at = $startedAt
                finished_at = [datetimeoffset]::UtcNow.ToString("o")
                prompt_archive = [string]$state.active_prompt_archive
                claude_log = $resumeLog
                git_status_after = $afterStatus
                changed_files = $changedFiles
                resumed = $true
            }
            Write-JsonAtomic -Path $DonePath -Value $done

            if (Test-ClaudeQuotaFailure -LogPath $resumeLog) {
                Start-QuotaBarrier -Actor "claude" -Reason "Claude Code quota limit detected during resume" `
                    -ResumeStatus "claude_resume" -ClaudeReset $ClaudeResetAt -CodexReset $CodexResetAt
            }
            elseif ($exitCode -eq 0) {
                Update-State -NewStatus "awaiting_codex_review" -Message "Resumed Claude cycle $($state.cycle) completed" | Out-Null
            }
            else {
                Update-State -NewStatus "claude_failed" -Message "Resumed Claude cycle failed with exit code $exitCode" | Out-Null
            }
        }
        elseif ($state.status -in @("awaiting_codex_review", "claude_failed")) {
            if ([bool]$config.direct_handoff_enabled) {
                Invoke-DirectCodexReview
                continue
            }
            Write-Host "Waiting for Codex heartbeat. status=$($state.status)"
        }
        elseif ($state.status -eq "codex_resume") {
            Invoke-DirectCodexReview -Resume
            continue
        }
        elseif ($state.status -eq "codex_review_running") {
            if (-not [string]::IsNullOrWhiteSpace([string]$state.updated_at)) {
                $reviewAge = [datetimeoffset]::UtcNow - [datetimeoffset]::Parse([string]$state.updated_at)
                if ($reviewAge.TotalMinutes -ge [double]$config.codex_review_timeout_minutes) {
                    Start-QuotaBarrier -Actor "codex" -Reason "Codex review watchdog timeout" `
                        -ResumeStatus ([string]$state.status) -ClaudeReset $ClaudeResetAt -CodexReset $CodexResetAt
                    continue
                }
            }
            Write-Host "Direct Codex review is running."
        }
        else {
            Update-State -NewStatus "blocked" -Message "Unknown automation state: $($state.status)" | Out-Null
            continue
        }

        if ($Once) {
            break
        }
        Start-Sleep -Seconds ([int]$config.poll_seconds)
    }
}
finally {
    if ($ownsMutex) {
        $mutex.ReleaseMutex()
    }
    $mutex.Dispose()
}
