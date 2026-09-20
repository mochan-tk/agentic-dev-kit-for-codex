# Thin PowerShell entry; the same Bash updater owns validation and recovery.
$ErrorActionPreference = 'Stop'
if (Test-Path Env:SCAFFOLD_SOURCE_DIR) { throw 'Local source override is not supported by network update.' }
function Find-GitBash {
    $candidates = @(
        "$env:ProgramFiles\Git\bin\bash.exe",
        "${env:ProgramFiles(x86)}\Git\bin\bash.exe",
        "$env:LocalAppData\Programs\Git\bin\bash.exe"
    ) | Where-Object { $_ -match '^[A-Za-z]:\\' }
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    }
    $systemRoot = $env:SystemRoot
    if (-not $systemRoot) { $systemRoot = 'C:\Windows' }
    $sys32 = $systemRoot.TrimEnd('\') + '\System32'
    $onPath = @(Get-Command bash.exe -All -CommandType Application -ErrorAction SilentlyContinue) |
        Where-Object { $_.Source -and -not $_.Source.StartsWith($sys32, [System.StringComparison]::OrdinalIgnoreCase) } |
        Select-Object -First 1
    if ($onPath) { return $onPath.Source }
    return $null
}
$bash = Find-GitBash
if (-not $bash) { throw 'Git for Windows Git Bash is required; WSL is not substituted.' }
$forward = @($args | ForEach-Object { "$_" })
$savedPath = $MyInvocation.MyCommand.Path
$updater = $null
$temporary = $null
$code = 1
try {
    if ($savedPath) {
        $adjacent = Join-Path (Split-Path -Parent $savedPath) 'scaffold-update.sh'
        if (Test-Path -LiteralPath $adjacent -PathType Leaf) { $updater = $adjacent }
    }
    if (-not $updater) {
        $repo = $env:SCAFFOLD_REPO
        if (-not $repo) { $repo = 'mochan-tk/agentic-dev-kit-for-codex' }
        if ($repo -notmatch '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$') { throw 'Invalid source repository.' }
        $ref = $env:SCAFFOLD_UPDATE_REF
        if (-not $ref) { $ref = 'main' }
        $url = 'https://raw.githubusercontent.com/' + $repo + '/' + [Uri]::EscapeDataString($ref) + '/.github/scripts/scaffold-update.sh'
        $temporary = Join-Path ([IO.Path]::GetTempPath()) ('scaffold-update-' + [IO.Path]::GetRandomFileName() + '.sh')
        Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $temporary
        $updater = $temporary
    }
    $global:LASTEXITCODE = $null
    & $bash ($updater -replace '\\', '/') @forward
    if ($null -eq $global:LASTEXITCODE) { throw 'Git Bash returned no exit status.' }
    $code = $global:LASTEXITCODE
} finally {
    if ($temporary) { Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue }
}
if ($savedPath) { exit $code }
if ($code -ne 0) { throw "scaffold-update.sh exited with code $code." }
