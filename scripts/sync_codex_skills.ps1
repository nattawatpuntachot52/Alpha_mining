<#
.SYNOPSIS
Sync all skills containing SKILL.md from Alpha_mining/skills/ into Codex skills.

.DESCRIPTION
Copies (default) or creates directory junctions (-Junction) for each skill in
Alpha_mining/skills/ into $CodexHome\skills (default: $env:CODEX_HOME or ~\.codex).
Refuses to overwrite existing targets unless -Force is specified.
#>
[CmdletBinding()]
param(
    [switch]$Junction,
    [switch]$Force,
    [switch]$DryRun,
    [string]$CodexHome = $(if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME '.codex' }),
    [switch]$Help
)

$ErrorActionPreference = 'Stop'

if ($Help) {
    Write-Output @"
Usage: scripts\sync_codex_skills.ps1 [-Junction] [-Force] [-DryRun] [-CodexHome <path>] [-Help]

Parameters:
  -Junction    Create directory junctions instead of copying (auto-tracks git pull; no admin required)
  -Force       Replace existing skill entries with the same names
  -DryRun      Show planned actions without modifying files
  -CodexHome   Override target CODEX_HOME (default: `$env:CODEX_HOME or ~\.codex)
  -Help        Show this help message
"@
    exit 0
}

$RepoRoot = Split-Path -Parent $PSScriptRoot
$SourceSkillsDir = Join-Path $RepoRoot 'skills'

if (-not (Test-Path -LiteralPath $SourceSkillsDir -PathType Container)) {
    throw "Skills directory not found: $SourceSkillsDir"
}

$Skills = Get-ChildItem -LiteralPath $SourceSkillsDir -Directory | Where-Object {
    Test-Path -LiteralPath (Join-Path $_.FullName 'SKILL.md') -PathType Leaf
}

if (-not $Skills -or $Skills.Count -eq 0) {
    throw "No skills containing SKILL.md found in $SourceSkillsDir"
}

$DestSkillsDir = Join-Path $CodexHome 'skills'

# Pre-flight check before modifying anything.
$Conflicts = @()
foreach ($Skill in $Skills) {
    $Dest = Join-Path $DestSkillsDir $Skill.Name
    if (Test-Path -LiteralPath $Dest) {
        $Conflicts += $Dest
    }
}

if (-not $Force -and $Conflicts.Count -gt 0) {
    Write-Error ("Refusing to overwrite existing skill path(s) without -Force:`n  - " + ($Conflicts -join "`n  - "))
    exit 1
}

if (-not $DryRun) {
    New-Item -ItemType Directory -Force -Path $DestSkillsDir | Out-Null
}

$ModeName = if ($Junction) { 'junction' } else { 'copy' }

foreach ($Skill in $Skills) {
    $Src = $Skill.FullName
    $Dest = Join-Path $DestSkillsDir $Skill.Name

    if ($DryRun) {
        if (Test-Path -LiteralPath $Dest) {
            Write-Output "[dry-run] replace $Dest ($ModeName -> $Src)"
        } else {
            Write-Output "[dry-run] $ModeName $Src -> $Dest"
        }
        continue
    }

    if (Test-Path -LiteralPath $Dest) {
        $Item = Get-Item -LiteralPath $Dest -Force
        if ($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            # Delete only the junction/symlink reparse point without touching target files.
            [System.IO.Directory]::Delete($Dest)
        } else {
            Remove-Item -LiteralPath $Dest -Recurse -Force -ErrorAction Stop
        }
    }

    if ($Junction) {
        New-Item -ItemType Junction -Path $Dest -Target $Src -ErrorAction Stop | Out-Null
        Write-Output "linked (junction): $Dest -> $Src"
    } else {
        Copy-Item -LiteralPath $Src -Destination $Dest -Recurse -ErrorAction Stop
        Write-Output "copied: $Src -> $Dest"
    }
}
