# Source-derived Git Bash entrypoint; all installer logic stays in adjacent Bash.
# No download, TLS mutation, WSL substitution, or account operation.
$ErrorActionPreference = 'Stop'
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
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$installer = Join-Path $here 'scaffold-init.sh'
if (-not (Test-Path -LiteralPath $installer -PathType Leaf)) { throw 'Adjacent scaffold-init.sh is missing.' }
$forward = @($args | ForEach-Object { "$_" })
& $bash ($installer -replace '\\', '/') @forward
exit $LASTEXITCODE
