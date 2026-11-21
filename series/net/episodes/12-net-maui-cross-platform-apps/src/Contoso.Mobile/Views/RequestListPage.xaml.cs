using Contoso.Mobile.Core.ViewModels;

namespace Contoso.Mobile.Views;

public partial class RequestListPage : ContentPage
{
	private readonly RequestListViewModel _viewModel;

	public RequestListPage(RequestListViewModel viewModel)
	{
		InitializeComponent();
		BindingContext = _viewModel = viewModel;
	}

	protected override void OnAppearing()
	{
		base.OnAppearing();
		_viewModel.RefreshCommand.Execute(null);   // every time the page is shown, including after "New" closes
	}

	private async void OnNewClicked(object? sender, EventArgs e)
	{
		if (Shell.Current is { } shell) await shell.GoToAsync("new");
	}
}
