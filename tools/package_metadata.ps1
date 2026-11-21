param(
    [Parameter(Mandatory)]
    [string]$Path
)

$ErrorActionPreference = 'Stop'
$file = Get-Item -LiteralPath $Path
if ($file.Extension -eq '.exe') {
    $reader = [IO.BinaryReader]::new($file.OpenRead())
    try {
        if ($reader.ReadUInt16() -ne 0x5a4d) { throw "$Path is not a Windows executable." }
        $reader.BaseStream.Position = 0x3c
        $reader.BaseStream.Position = $reader.ReadUInt32()
        if ($reader.ReadUInt32() -ne 0x4550) { throw "$Path has an invalid PE header." }
        @{ ProductVersion = $file.VersionInfo.ProductVersion; Machine = $reader.ReadUInt16() } |
            ConvertTo-Json -Compress
    } finally {
        $reader.Dispose()
    }
    return
}

$installer = New-Object -ComObject WindowsInstaller.Installer
$database = $installer.GetType().InvokeMember(
    'OpenDatabase', 'InvokeMethod', $null, $installer, @($file.FullName, 0)
)

function Read-MsiProperty([string]$Name) {
    $query = 'SELECT `Value` FROM `Property` WHERE `Property` = ''{0}''' -f $Name
    $view = $database.GetType().InvokeMember('OpenView', 'InvokeMethod', $null, $database, @($query))
    try {
        $null = $view.GetType().InvokeMember('Execute', 'InvokeMethod', $null, $view, $null)
        $record = $view.GetType().InvokeMember('Fetch', 'InvokeMethod', $null, $view, $null)
        if ($null -ne $record) {
            $record.GetType().InvokeMember('StringData', 'GetProperty', $null, $record, @(1))
        }
    } finally {
        $null = $view.GetType().InvokeMember('Close', 'InvokeMethod', $null, $view, $null)
    }
}

$summary = $database.GetType().InvokeMember('SummaryInformation', 'GetProperty', $null, $database, @(0))
$metadata = @{
    Template = $summary.GetType().InvokeMember('Property', 'GetProperty', $null, $summary, @(7))
}
foreach ($name in @('ProductName', 'Manufacturer', 'ProductVersion', 'ProductCode', 'UpgradeCode', 'ALLUSERS', 'MSIINSTALLPERUSER')) {
    $metadata[$name] = Read-MsiProperty $name
}
$metadata | ConvertTo-Json -Compress
