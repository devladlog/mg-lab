@{
    # Root folder for all lab files. 'auto' = the fixed drive with the most free space (\MGLab on that drive).
    LabRoot      = 'auto'
    MinFreeGB    = 120

    Domain       = 'lab.contoso.com'
    NetBIOS      = 'CONTOSO'
    TimeZone     = 'GMT Standard Time'
    Locale       = 'en-US'
    InputLocale  = '0816:00000816'   # Portuguese (Portugal) keyboard

    Switch       = @{ Name = 'MGLab-NAT'; Prefix = '10.20.0'; PrefixLength = 24; Gateway = '10.20.0.1' }

    Media = @{
        # Windows Server 2025 evaluation ISO (Microsoft Evaluation Center, 180-day eval)
        ServerIso = 'https://go.microsoft.com/fwlink/p/?LinkID=2268694&clcid=0x409&culture=en-us&country=US'
        # SQL Server 2022 evaluation bootstrapper (Evaluation Center); installed with the free Developer edition key
        SqlSetup  = 'https://go.microsoft.com/fwlink/?linkid=2215202&clcid=0x409&culture=en-us&country=us'
    }

    # Image: 'Core' = Datacenter Evaluation (Server Core), 'Desktop' = Datacenter Evaluation (Desktop Experience)
    VMs = @(
        @{ Name = 'CON-DC01';  Role = 'DC';     Image = 'Core';    vCPU = 2; StartupGB = 2; MaxGB = 3; DiskGB = 60;  IP = 10 }
        @{ Name = 'CON-SRV01'; Role = 'Member'; Image = 'Core';    vCPU = 2; StartupGB = 1; MaxGB = 2; DiskGB = 60;  IP = 21 }
        @{ Name = 'CON-SRV02'; Role = 'Member'; Image = 'Desktop'; vCPU = 2; StartupGB = 2; MaxGB = 3; DiskGB = 60;  IP = 22 }
        @{ Name = 'CON-SQL01'; Role = 'SQL';    Image = 'Core';    vCPU = 2; StartupGB = 2; MaxGB = 6; DiskGB = 100; IP = 30 }
    )
}
