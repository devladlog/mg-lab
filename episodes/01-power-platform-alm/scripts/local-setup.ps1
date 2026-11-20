# MG Lab - Episode 1: local pac CLI workflow
# Requires: Power Platform CLI (winget install Microsoft.PowerAppsCLI, or the VS Code "Power Platform Tools" extension)

# 1. Authenticate to DEV (interactive for local work; pipelines use a service principal)
pac auth create --name mglab-dev --environment "https://mglab-dev.crm4.dynamics.com"
pac auth list
pac org who

# 2. Export the solution as unmanaged AND managed
pac solution export --name MGLabDemo --path .\out\MGLabDemo.zip --overwrite
pac solution export --name MGLabDemo --path .\out\MGLabDemo_managed.zip --managed --overwrite

# 3. Unpack both into source control
pac solution unpack --zipfile .\out\MGLabDemo.zip --folder .\src\MGLabDemo --packagetype Both --allowDelete

# 4. Generate a deployment settings template from the solution (env vars + connection refs)
pac solution create-settings --solution-zip .\out\MGLabDemo_managed.zip --settings-file .\settings\deployment-settings.template.json

# 5. Pack a managed build from source (what the pipeline does)
pac solution pack --zipfile .\out\MGLabDemo_managed.zip --folder .\src\MGLabDemo --packagetype Managed

# 6. Static analysis before you open a PR
pac solution check --path .\out\MGLabDemo_managed.zip --geo Europe --outputDirectory .\out\checker
