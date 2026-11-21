using Android.App;
using Android.Runtime;

namespace Contoso.Mobile;

// Learn (local web services): cleartext HTTP to the dev machine only in Debug builds. Release builds stay HTTPS-only.
// Note: UsesCleartextTraffic is ignored on Android 7.0+ when a network security config file is present (we have one, see
// Resources/xml/network_security_config.xml), so this attribute is belt and braces for older devices.
#if DEBUG
[Application(UsesCleartextTraffic = true)]
#else
[Application]
#endif
public class MainApplication : MauiApplication
{
	public MainApplication(IntPtr handle, JniHandleOwnership ownership)
		: base(handle, ownership)
	{
	}

	protected override MauiApp CreateMauiApp() => MauiProgram.CreateMauiApp();
}
