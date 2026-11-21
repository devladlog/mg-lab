using 'main.bicep'

// Pass the key on the command line instead of committing it:
//   az deployment group create ... -p adminPublicKey="$(cat ./zt-lab.pub)"
param adminPublicKey = 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPLACEHOLDERPLACEHOLDERPLACEHOLDERPLACEHOLDER throwaway-lab-key'
param namePrefix = 'mgl09'
