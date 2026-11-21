param(
    [Parameter(Mandatory)]
    [string]$Version,
    [string]$Installer,
    [string]$OlderInstaller
)

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$scratch = New-Item -ItemType Directory -Path (Join-Path $root "build/smoke-$([guid]::NewGuid())")

function Assert-Condition([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

function Test-Application([string]$Exe, [PSCredential]$Credential, [switch]$OneFile) {
    $parameters = @{ FilePath = $Exe; WorkingDirectory = Split-Path $Exe -Parent; PassThru = $true }
    if ($Credential) {
        $parameters.Credential = $Credential
        $parameters.LoadUserProfile = $true
    }
    $process = Start-Process @parameters
    $windowProcess = $process
    try {
        $deadline = [DateTime]::UtcNow.AddSeconds(60)
        do {
            $process.Refresh()
            if ($process.HasExited) { throw "$Exe exited early with code $($process.ExitCode)." }
            if ($OneFile) {
                $child = Get-CimInstance Win32_Process -Filter "ParentProcessId = $($process.Id)" |
                    Where-Object ExecutablePath -eq $Exe | Select-Object -First 1
                if ($child) { $windowProcess = Get-Process -Id $child.ProcessId }
            }
            $windowProcess.Refresh()
            if ($windowProcess.MainWindowTitle -eq "Mod Manager v$Version") { break }
            Start-Sleep -Milliseconds 250
        } while ([DateTime]::UtcNow -lt $deadline)
        Assert-Condition ($windowProcess.MainWindowTitle -eq "Mod Manager v$Version") "$Exe did not open its main window."
        Assert-Condition ($windowProcess.CloseMainWindow()) "Could not close the main window for $Exe."
        Assert-Condition ($process.WaitForExit(20000)) "$Exe did not exit after closing its main window."
        Assert-Condition ($process.ExitCode -eq 0) "$Exe exited with code $($process.ExitCode)."
    } finally {
        $process.Refresh()
        if (-not $process.HasExited) { $process.Kill($true) }
        $process.Dispose()
    }
}

function Invoke-Installer([string]$Action, [string]$Path, [string]$Log, [int]$ExpectedCode = 0) {
    $arguments = @($Action, ('"{0}"' -f $Path), '/qn', '/norestart', '/L*v', ('"{0}"' -f $Log))
    $process = Start-Process -FilePath "$env:SystemRoot/System32/msiexec.exe" -ArgumentList $arguments -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne $ExpectedCode) {
        Get-Content -LiteralPath $Log -Tail 60 -ErrorAction SilentlyContinue | Write-Host
        throw "msiexec $Action returned $($process.ExitCode), expected $ExpectedCode."
    }
}

if (-not $Installer) {
    $onedir = New-Item -ItemType Directory -Path (Join-Path $scratch 'onedir')
    $onefile = New-Item -ItemType Directory -Path (Join-Path $scratch 'onefile')
    Copy-Item -LiteralPath (Join-Path $root 'dist/mod-manager-gui/mod-manager-gui.exe') -Destination $onedir
    Copy-Item -LiteralPath (Join-Path $root 'dist/mod-manager-gui/_internal') -Destination $onedir -Recurse
    Copy-Item -LiteralPath (Join-Path $root 'dist/mod-manager-gui.exe') -Destination $onefile
    foreach ($directory in @($onedir.FullName, $onefile.FullName)) {
        $exe = Join-Path $directory 'mod-manager-gui.exe'
        Assert-Condition ((Get-Item -LiteralPath $exe).VersionInfo.ProductVersion -eq $Version) "Incorrect EXE version in $directory."
        Test-Application $exe -OneFile:($directory -eq $onefile.FullName)
        Assert-Condition (Test-Path -LiteralPath (Join-Path $directory 'config.json')) "No portable config was saved in $directory."
    }
    Write-Host 'Both portable executables opened, saved settings and exited successfully.'
    return
}

$metadataReader = Join-Path $PSScriptRoot 'package_metadata.ps1'
$new = & $metadataReader $Installer | ConvertFrom-Json
$old = & $metadataReader $OlderInstaller | ConvertFrom-Json
$installerPath = (Resolve-Path -LiteralPath $Installer).Path
$olderPath = (Resolve-Path -LiteralPath $OlderInstaller).Path
$installDirectory = Join-Path $env:ProgramFiles 'Mod Manager'
$exe = Join-Path $installDirectory 'mod-manager-gui.exe'
$shortcut = Join-Path ([Environment]::GetFolderPath('CommonPrograms')) 'Mod Manager.lnk'
$arpRoot = 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall'
$newEntry = Join-Path $arpRoot $new.ProductCode
$oldEntry = Join-Path $arpRoot $old.ProductCode
Assert-Condition ($new.ProductVersion -eq $Version -and [version]$old.ProductVersion -lt [version]$Version -and
                  $new.UpgradeCode -eq $old.UpgradeCode -and $new.ProductCode -ne $old.ProductCode) 'Invalid upgrade fixture.'
Assert-Condition (-not (Test-Path -LiteralPath $installDirectory) -and
                  -not (Test-Path -LiteralPath $newEntry) -and -not (Test-Path -LiteralPath $oldEntry)) (
    'Run MSI smoke testing on a disposable Windows system without an existing Mod Manager installation.'
)

$username = 'ModSmoke' + [guid]::NewGuid().ToString('N').Substring(0, 10)
$password = ConvertTo-SecureString ([Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(24)) + 'aA1!') -AsPlainText -Force
$user = New-LocalUser -Name $username -Password $password
try {
    $usersGroup = 'S-1-5-32-545'
    if (-not (Get-LocalGroupMember -SID $usersGroup | Where-Object SID -eq $user.SID)) {
        Add-LocalGroupMember -SID $usersGroup -Member $user
    }
    $credential = [PSCredential]::new("$env:COMPUTERNAME\$username", $password)
    Invoke-Installer '/i' $olderPath (Join-Path $scratch 'msi-install.log')
    Assert-Condition ((Get-ItemProperty -LiteralPath $oldEntry).DisplayVersion -eq $old.ProductVersion) 'The first install did not register under HKLM.'
    Assert-Condition (Test-Path -LiteralPath $shortcut) 'The common Start Menu shortcut is missing.'
    Test-Application $exe $credential
    $profile = Get-CimInstance Win32_UserProfile -Filter "SID = '$($user.SID.Value)'"
    $data = Join-Path $profile.LocalPath 'AppData/Local/Mod Manager'
    $config = Join-Path $data 'config.json'
    $settings = Get-Content -LiteralPath $config -Raw | ConvertFrom-Json
    Assert-Condition ($settings.window_width -gt 0) 'The standard user did not persist application settings.'
    Assert-Condition (Test-Path -LiteralPath (Join-Path $data 'mod-manager.log')) 'The standard user log is missing.'
    Assert-Condition (-not (Test-Path -LiteralPath (Join-Path $installDirectory 'config.json'))) 'Settings were written to Program Files.'
    $configHash = (Get-FileHash -LiteralPath $config).Hash
    $profiles = New-Item -ItemType Directory -Path (Join-Path $data 'profiles') -Force
    $profileData = Join-Path $profiles 'default-imports.json'
    Set-Content -LiteralPath $profileData -Value '{}' -Encoding utf8
    $profileHash = (Get-FileHash -LiteralPath $profileData).Hash

    Invoke-Installer '/i' $installerPath (Join-Path $scratch 'msi-upgrade.log')
    Assert-Condition (-not (Test-Path -LiteralPath $oldEntry)) 'Upgrade left the previous product registered.'
    Assert-Condition ((Get-ItemProperty -LiteralPath $newEntry).DisplayVersion -eq $Version) 'The upgrade did not register the expected version.'
    Assert-Condition ((Get-FileHash -LiteralPath $config).Hash -eq $configHash) 'Upgrade altered user settings.'
    Assert-Condition ((Get-FileHash -LiteralPath $profileData).Hash -eq $profileHash) 'Upgrade altered profile data.'
    Test-Application $exe $credential
    $configHash = (Get-FileHash -LiteralPath $config).Hash

    Invoke-Installer '/i' $olderPath (Join-Path $scratch 'msi-downgrade.log') -ExpectedCode 1603
    Assert-Condition ((Get-ItemProperty -LiteralPath $newEntry).DisplayVersion -eq $Version) 'Downgrade modified the installed product.'
    Invoke-Installer '/x' $new.ProductCode (Join-Path $scratch 'msi-uninstall.log')
    Assert-Condition (-not (Test-Path -LiteralPath $newEntry) -and -not (Test-Path -LiteralPath $exe) -and
                      -not (Test-Path -LiteralPath $shortcut)) 'Uninstall left registered product files or shortcuts.'
    Assert-Condition ((Get-FileHash -LiteralPath $config).Hash -eq $configHash) 'Uninstall altered user settings.'
    Assert-Condition ((Get-FileHash -LiteralPath $profileData).Hash -eq $profileHash) 'Uninstall altered profile data.'
    Write-Host 'Machine install, standard-user launch, upgrade, downgrade prevention and data preservation passed.'
} finally {
    Remove-LocalUser -SID $user.SID
}
