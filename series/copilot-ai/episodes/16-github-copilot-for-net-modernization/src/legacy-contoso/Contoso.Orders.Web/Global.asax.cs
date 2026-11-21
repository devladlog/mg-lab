using System.Diagnostics;
using System.Web;
using System.Web.Mvc;
using System.Web.Routing;

namespace Contoso.Orders.Web
{
    public class MvcApplication : HttpApplication
    {
        protected void Application_Start()
        {
            AreaRegistration.RegisterAllAreas();
            RouteConfig.RegisterRoutes(RouteTable.Routes);
        }

        protected void Application_Error()
        {
            var error = Server.GetLastError();
            Trace.TraceError("Unhandled: " + error);
        }
    }
}
