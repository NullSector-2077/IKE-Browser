# Workflow helper: says which Media Foundation decoders this Windows has.
# The runners are Windows Server, where Media Foundation is an optional
# feature; a desktop Windows 10 / 11 has it (the N editions only with the
# Media Feature Pack). Nothing here is shipped.
$ErrorActionPreference = "Continue"
Get-CimInstance Win32_OperatingSystem | Select-Object Caption, Version, BuildNumber | Format-List
try { Get-WindowsFeature Server-Media-Foundation | Format-Table Name, InstallState }
catch { "Get-WindowsFeature: $_" }

$names = "mfplat.dll", "msmpeg2vdec.dll", "msauddecmft.dll"
function Show-Decoders {
    foreach ($name in $names) {
        $path = Join-Path $env:SystemRoot "System32\$name"
        if (Test-Path $path) {
            "{0}: present, version {1}" -f $name, (Get-Item $path).VersionInfo.ProductVersion
        } else {
            "{0}: MISSING" -f $name
        }
    }
}
Show-Decoders

# With -InstallFeature: make this Windows Server like a desktop Windows, where
# Media Foundation is always there.
if ($args -contains "-InstallFeature") {
    try {
        $feature = Get-WindowsFeature Server-Media-Foundation
        if ($feature -and -not $feature.Installed) {
            "Installing the Media Foundation feature of Windows Server"
            Install-WindowsFeature Server-Media-Foundation |
                Format-List Success, RestartNeeded, ExitCode
            Show-Decoders
        }
    } catch { "Install-WindowsFeature: $_" }
}
"Graphics adapters:"
Get-CimInstance Win32_VideoController |
    Select-Object Name, DriverVersion, AdapterCompatibility | Format-List
exit 0
