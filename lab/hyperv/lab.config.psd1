@{
    # Root folder for all lab files. 'auto' = the fixed drive with the most free space (\MGLab on that drive).
    # E: is this laptop's dedicated volume for large artifacts (auto would pick C:, the OS drive).
    LabRoot      = 'E:\MGLab'
    MinFreeGB    = 120

    Domain       = 'lab.contoso.com'
    NetBIOS      = 'CONTOSO'
    TimeZone     = 'GMT Standard Time'
    Locale       = 'en-US'
    InputLocale  = '0816:00000816'   # Portuguese (Portugal) keyboard

    # 10.50.0.0/24: the laptop already has static routes for 10.50.0.0/16 (via the router, on Ethernet).
    Switch       = @{ Name = 'MGLab-NAT'; Prefix = '10.50.0'; PrefixLength = 24; Gateway = '10.50.0.1' }

    Media = @{
        # Windows Server 2025 evaluation ISO (Microsoft Evaluation Center, 180-day eval), build 26100.1742, ~6 GB.
        # (LinkID 2268694 pointed at the retired preview build and now returns HTTP 400.)
        ServerIso = 'https://go.microsoft.com/fwlink/?linkid=2293312&clcid=0x409&culture=en-us&country=us'
        # SQL Server 2022 Developer edition ISO (free, non-production), ~1.1 GB. Downloaded directly: the SSEI
        # bootstrapper's quiet /ACTION=Download exited without downloading anything.
        SqlIso    = 'https://download.microsoft.com/download/3/8/d/38de7036-2433-4207-8eae-06e247e17b25/SQLServer2022-x64-ENU-Dev.iso'
    }

    # Image: 'Core' = Datacenter Evaluation (Server Core), 'Desktop' = Datacenter Evaluation (Desktop Experience)
    VMs = @(
        @{ Name = 'CON-DC01';  Role = 'DC';     Image = 'Core';    vCPU = 2; StartupGB = 2; MaxGB = 3; DiskGB = 60;  IP = 10 }
        @{ Name = 'CON-SRV01'; Role = 'Member'; Image = 'Core';    vCPU = 2; StartupGB = 1; MaxGB = 2; DiskGB = 60;  IP = 21 }
        @{ Name = 'CON-SRV02'; Role = 'Member'; Image = 'Desktop'; vCPU = 2; StartupGB = 2; MaxGB = 3; DiskGB = 60;  IP = 22 }
        @{ Name = 'CON-CLI01'; Role = 'Member'; Image = 'Core';    vCPU = 1; StartupGB = 1; MaxGB = 1.5; DiskGB = 60; IP = 41 }
        @{ Name = 'CON-SQL01'; Role = 'SQL';    Image = 'Core';    vCPU = 2; StartupGB = 2; MaxGB = 6; DiskGB = 100; IP = 30 }
    )
}
