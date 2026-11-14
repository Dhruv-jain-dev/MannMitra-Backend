$ErrorActionPreference = 'Stop'

$envPath = Join-Path (Get-Location) '.env'
$backupPath = 'C:\Users\hp\MannMitra-env-backups\.env.before-new-pooler-20261114'
$expectedHost = 'aws-0-ap-southeast-2.pooler.supabase.com'
$expectedPort = 5432
$expectedDatabase = 'postgres'

if (-not (Test-Path -LiteralPath $envPath)) { throw 'Root .env was not found.' }
if (-not (Test-Path -LiteralPath $backupPath)) { throw 'External .env backup is missing; refusing to continue.' }

$lines = Get-Content -LiteralPath $envPath
$urlLineIndex = -1
for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match '^\s*DATABASE_URL\s*=') {
        if ($urlLineIndex -ge 0) { throw 'Multiple DATABASE_URL entries found.' }
        $urlLineIndex = $i
    }
}
if ($urlLineIndex -lt 0) { throw 'DATABASE_URL entry was not found.' }

$currentUrl = ($lines[$urlLineIndex] -replace '^\s*DATABASE_URL\s*=\s*', '')
$urlQuote = ''
if (($currentUrl.StartsWith("'") -and $currentUrl.EndsWith("'")) -or ($currentUrl.StartsWith('"') -and $currentUrl.EndsWith('"'))) {
    $urlQuote = $currentUrl.Substring(0, 1)
    $currentUrl = $currentUrl.Substring(1, $currentUrl.Length - 2)
}
$targetMatch = [regex]::Match(
    $currentUrl,
    '^(?:postgresql(?:\+psycopg)?://)(?<userinfo>[^@]+)@(?<host>[^/:?#]+)(?::(?<port>[0-9]+))(?<path>/[^?#]*)?(?:\?.*)?$'
)
if (-not $targetMatch.Success) {
    throw 'DATABASE_URL is not a supported PostgreSQL URL.'
}
$userinfo = $targetMatch.Groups['userinfo'].Value
$userinfoParts = $userinfo.Split(':', 2)
$configuredUsername = $userinfoParts[0]
$configuredHost = $targetMatch.Groups['host'].Value
$configuredPort = [int]$targetMatch.Groups['port'].Value
$configuredDatabase = $targetMatch.Groups['path'].Value.Trim('/')
if (-not $configuredUsername.StartsWith('postgres.') -or $configuredUsername.Length -le 9) {
    throw 'DATABASE_URL username is not a Supabase project-scoped postgres username.'
}
if ($configuredHost -ne $expectedHost -or $configuredPort -ne $expectedPort -or $configuredDatabase -ne $expectedDatabase) {
    throw 'Existing DATABASE_URL target does not match the verified new project.'
}

$securePassword = Read-Host 'Enter the NEW Supabase database password' -AsSecureString
$passwordPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
try {
    $password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPtr)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPtr)
}
if ([string]::IsNullOrEmpty($password)) { throw 'Password was empty.' }

$encodedPassword = [Uri]::EscapeDataString($password)
$credentialPattern = '^(?<prefix>postgresql(?:\+psycopg)?://)(?<username>[^:/@]+):(?<password>[^@]*)@(?<rest>.+)$'
$credentialMatch = [regex]::Match($currentUrl, $credentialPattern)
if (-not $credentialMatch.Success) {
    throw 'DATABASE_URL credentials could not be parsed safely.'
}
$passwordStart = $credentialMatch.Groups['password'].Index
$passwordLength = $credentialMatch.Groups['password'].Length
$updatedUrl = $currentUrl.Substring(0, $passwordStart) + $encodedPassword + $currentUrl.Substring($passwordStart + $passwordLength)
if ($updatedUrl -notmatch '^postgresql(?:\+psycopg)?://') {
    throw 'Could not replace only the password component.'
}

$lines[$urlLineIndex] = 'DATABASE_URL=' + $urlQuote + $updatedUrl + $urlQuote
[IO.File]::WriteAllLines($envPath, $lines, (New-Object Text.UTF8Encoding($false)))
$password = $null
$encodedPassword = $null
$updatedUrl = $null
Write-Output 'DATABASE_URL_PASSWORD_UPDATED=YES'
Write-Output 'EXTERNAL_BACKUP_PRESERVED=YES'
Write-Output 'TARGET_HOST_PORT_DATABASE_PRESERVED=YES'
