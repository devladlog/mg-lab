# Timer trigger: one sync pass every few minutes (Onboarding__Schedule, NCRONTAB). The timer trigger runs a single
# instance across scale-out and does not retry a failed run: the next schedule is the retry.
param($Timer)

$ErrorActionPreference = 'Stop'
Import-Module OnboardingSync   # from ./Modules, which the PowerShell worker adds to PSModulePath

if ($Timer -and $Timer.IsPastDue) { Write-Warning 'Timer is past due; running now.' }

$config = Get-OnbConfigFromEnvironment
$results = Invoke-OnbSync -Config $config

foreach ($r in $results) {
    $line = 'Request {0}: {1} -> {2} ({3}). {4}' -f $r.ItemId, $r.From, $r.To, $r.Outcome, $r.Note
    if ($r.Outcome -eq 'Conflict') { Write-Warning "$line Item changed while we worked; it will be retried." }
    else { Write-Information $line -InformationAction Continue }
}
Write-Information ("Sync finished: {0} item(s) changed." -f @($results | Where-Object Outcome -eq 'Updated').Count) -InformationAction Continue
