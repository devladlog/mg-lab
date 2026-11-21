using Contoso.Mobile.Views;

namespace Contoso.Mobile;

public partial class AppShell : Shell
{
	public AppShell()
	{
		InitializeComponent();
		Routing.RegisterRoute("new", typeof(NewRequestPage));   // GoToAsync("new") from the list page; ".." goes back
	}
}
