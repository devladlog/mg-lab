<# MG Lab #6 — creates a fictional legacy file share to migrate (no real data). #>
param([string] $Path = './legacy-share', [int] $Seed = 6)
$rnd = [Random]::new($Seed)
$files = @{
    'Accounts'          = 'Budget 2025 Q1.xlsx', 'Budget 2025 Q2.xlsx', 'Invoice register.csv', 'Supplier contracts.pdf', 'Year-end checklist.docx', 'Expense policy.pdf', '~$Budget 2025 Q1.xlsx'
    'People'            = 'Onboarding checklist.docx', 'Leave policy.pdf', 'Org chart 2025.pptx', 'Training plan.xlsx', 'Contract: template v2.docx', 'Job description - Analyst.docx'
    'Ops'               = 'Warehouse layout.pdf', 'Shift roster.xlsx', 'Safety procedures.docx', 'Fleet maintenance.csv', 'Thumbs.db', 'Vendor SLA review.pptx'
    'Sales & Marketing' = 'Pipeline review Q3.pptx', 'Price list 2025.xlsx', 'Brand guidelines.pdf', 'Campaign plan.docx', 'Customer survey results.csv', 'Trade show notes.txt'
    'IT Support'        = 'Asset register.xlsx', 'Backup procedure.docx', 'Network diagram.pdf', 'Laptop refresh plan.pptx', 'empty.txt', 'Password policy.pdf'
}
foreach ($dept in $files.Keys) {
    $dir = Join-Path $Path $dept
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
    foreach ($name in $files[$dept]) {
        $file = Join-Path $dir $name
        if ($name -eq 'empty.txt') { New-Item -ItemType File -Path $file -Force | Out-Null }
        else {
            $bytes = [byte[]]::new($rnd.Next(2048, 48KB)); $rnd.NextBytes($bytes)
            [IO.File]::WriteAllBytes($file, $bytes)
        }
        (Get-Item -LiteralPath $file -Force).LastWriteTimeUtc = [datetime]'2019-01-01' + [timespan]::FromDays($rnd.Next(0, 2100))
    }
}
# A folder nobody mapped, and a path that is far too long for SharePoint
New-Item -ItemType Directory -Path (Join-Path $Path 'Archive') -Force | Out-Null
[IO.File]::WriteAllText((Join-Path $Path 'Archive/old proposal.docx'), 'legacy')
$long = Join-Path $Path ('Ops/' + ('Very long project folder name ' * 4).Trim())
New-Item -ItemType Directory -Path $long -Force | Out-Null
[IO.File]::WriteAllText((Join-Path $long (('Final report revision ' * 12).Trim() + '.docx')), 'legacy')
Get-ChildItem $Path -Recurse -File -Force | Measure-Object | ForEach-Object { "Created $($_.Count) files in $Path" }
