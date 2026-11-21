# The kind of script that "works on my machine": copied between servers for years.
param($Folder, $User, $Password)

function Create-Packs($rows) {
    foreach ($r in $rows) {
        Write-Host "Creating pack for $($r.Code)"
        $secure = ConvertTo-SecureString $Password -AsPlainText -Force
        try {
            Invoke-Expression "New-Item -ItemType Directory -Force $Folder\$($r.Department)"
        } catch { }
    }
}

$rows = Import-Csv .\requests.csv | ? { $_.budget -gt 0 }
Create-Packs $rows
gci $Folder -Recurse | % { $_.FullName }
