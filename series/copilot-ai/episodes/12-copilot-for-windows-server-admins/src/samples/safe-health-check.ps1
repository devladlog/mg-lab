# Hand-written example of a read-only script. The gate must report Clean in ReadOnly mode.
Get-Service -Name W32Time | Select-Object Name, Status, StartType
Get-ChildItem -Path C:\Windows\System32\drivers\etc -File | Select-Object Name, Length
Get-Date
