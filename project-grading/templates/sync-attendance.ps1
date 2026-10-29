# Sync the workbook's Attendance sheet to AthkaX (project-grading skill, athkax.py).
#   .\sync-attendance.ps1                 today's date, after showing the plan and asking to proceed
#   .\sync-attendance.ps1 -DryRun         plan only
#   .\sync-attendance.ps1 -Date 2026-10-25,2026-10-26
#   .\sync-attendance.ps1 -AllDates       every date column
# --no-skip-all-absent: a learner Absent on every day stays Absent (never-joined learners are Leave on the sheet).
param([string[]]$Date = @((Get-Date).ToString('yyyy-MM-dd')), [switch]$DryRun, [switch]$AllDates)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$env:PYTHONIOENCODING = 'utf-8'
$wb = Get-ChildItem "$PSScriptRoot\*.xlsx" | Where-Object { $_.Name -notlike 'chat-*' } | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $wb) { throw 'No workbook in the course folder' }
$argv = @('run', '-q', "$HOME\.claude\skills\project-grading\scripts\athkax.py", 'attendance', $wb.FullName, '--no-skip-all-absent')
if (-not $AllDates) { foreach ($d in $Date) { $argv += @('--date', $d) } }
if ($DryRun) { $argv += '--dry-run' }
Write-Host "Workbook: $($wb.Name)"
Write-Host "uv $($argv -join ' ')"
& uv @argv
