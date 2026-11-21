# Dot-source every function: Private files stay internal, Public files are exported by name in the manifest.
foreach ($folder in 'Private', 'Public') {
    foreach ($script in Get-ChildItem -Path (Join-Path $PSScriptRoot $folder) -Filter '*.ps1') {
        . $script.FullName
    }
}
