# Live-session recording — record.json brief

Every episode's screen scenes are recorded as **live sessions**: real commands typed and run on screen, real portal
clicks, real output, no edits, nothing faked. Each episode gets a `record.json` next to its `script.yaml`. The kit in
`series/tools/rec/` plays it on the recording laptop (Windows 11, Hyper-V host of the lab in `series/LAB.md`).

Read the episode's `demo.md` (its "Lab environment", preparation, "Screens to capture", masking and tear-down) and the
`screen` scenes in `script.yaml`. One `screens[]` entry per `screen` scene, `name` = the image file name without
folder and extension (`screens/live-run.jpg` -> `live-run`).

## Format
```json
{
  "prepare":  ["PowerShell statements run on the laptop before the first screen, NOT recorded"],
  "screens": [
    { "name": "live-run", "kind": "terminal",
      "target": "host | CON-CLI01 | CON-SRV02 | ...",       // host = the laptop; a VM name = PowerShell Direct into it
      "configurationName": "PowerShell.7",                     // optional: VM endpoint (pwsh 7 needs ENABLE_PSREMOTING at install)
      "workdir": "C:\\lab\\ep01\\src",                         // on the target
      "prompt": "PS C:\\lab\\ep01\\src> ",
      "prepare": ["optional, per screen, not recorded"],
      "commands": ["typed and run one by one, as on screen", "#pause 3"] },
    { "name": "portal", "kind": "browser",
      "url": "https://make.powerapps.com/",
      "account": "labadmin | alex.demo | sam.demo | ...",      // who must be signed in (the owner signs in; never write a password)
      "steps": ["Open Apps", "Select 'Contoso Inspections'", "..."],   // what to click, in order, as a person would
      "mask": ["tenant name in the top bar", "user e-mail in the account menu"] },
    { "name": "desktop", "kind": "app", "app": "Power BI Desktop | SSMS 22 | ...", "steps": ["..."], "mask": ["..."] }
  ],
  "teardown": ["PowerShell statements run on the laptop after the last screen, NOT recorded"],
  "needs": ["lab-vms", "tenant", "azure", "premium-trial", "paid:<what>", "licence:<what>", "docker", "api-key:<vendor>"],
  "blocked": "optional: one sentence when a screen cannot be recorded yet (missing licence, purchase, preview not available)"
}
```

## Rules
- **Real only.** Commands come from `demo.md`/`script.yaml`; never print canned output, never `Write-Host` a result.
  If a scene shows something only a person can see in a GUI, make it `browser` or `app` with clear steps.
- **Laptop facts** (see the "Recording laptop toolchain" section of `series/LAB.md`): Windows, PowerShell 7.6 and 5.1,
  Python 3.10 as `python` (not `python3`), Node 24, .NET 10 only, Git Bash for bash, Bicep via the Azure CLI's copy, no
  Docker unless listed in `needs`. The repo is at `D:\momento_galatico_kit\mg-lab-series`; `prepare` runs with the
  episode folder as the current directory.
- **Lab VMs:** use PowerShell Direct (`New-PSSession -VMName X -Credential $cred`, `Invoke-Command -VMName X -Credential
  $cred`). `$cred` (CONTOSO\Administrator) is provided by the kit: **never** `Get-Credential`, never a password in a file.
  Copy episode files to a VM with `Copy-Item -ToSession`. Make `prepare` idempotent (safe to run twice). VMs and IPs:
  `series/LAB.md` and `series/LAB-REQUESTS.md`. If the episode needs a VM that does not exist yet, add it to `needs` as
  `vm:<NAME>` and leave the screens defined.
- **Sign-ins** (`az login`, `Connect-MgGraph`, `Connect-PnPOnline`, `pac auth`, browser logins) are done by the owner:
  put them in `prepare` only as device-code or interactive commands with a comment `# owner signs in`, and list
  `tenant`/`azure` in `needs`. Never write a secret, a key, a password or a connection string with a password.
- **Masking:** list what must be hidden in each browser/app screen (tenant name, real domain, e-mail addresses,
  subscription/tenant ids). Terminal scenes must not print secrets (no `Get-Clixml ... .Password`, no `az account show`
  without `--query` that hides ids).
- **Cost:** anything billed (Azure resources, paid capacities, API keys) goes in `needs` and `teardown` must remove it.
- Keep `commands` short and readable on screen; split long scripts into several commands. Use `#pause N` after a result
  that the narration talks about.
- Write **only** `record.json` files in the episode folders you are given. No other file edits, no git, no browser, no
  sign-ins, no cloud calls. Run `python3 /home/claude/mglab/mg-lab/series/tools/rec/check_record.py <folders>` and fix every
  error before handing back.
