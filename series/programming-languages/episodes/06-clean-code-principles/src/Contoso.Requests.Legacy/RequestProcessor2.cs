using System.Globalization;

namespace Contoso.Requests.Legacy;

// Request processor (v2, do not touch, works)
public class RequestProcessor2
{
    private int cnt; // counter

    public int Count { get { return cnt; } }

    // process a line from the file
    // f = true -> mail
    public string Process(string l, bool f)
    {
        string r = "";
        cnt++;
        try
        {
            var p = l.Split(';');
            if (p.Length == 5)
            {
                if (p[0] != "" && p[0].StartsWith("PR-", StringComparison.Ordinal))
                {
                    decimal b = 0;
                    if (decimal.TryParse(p[3], NumberStyles.Any, CultureInfo.InvariantCulture, out b))
                    {
                        if (b > 0)
                        {
                            // budget >= 50k is high
                            string pr = "N";
                            if (b > 50000) pr = "H";
                            if (b >= 250000) pr = "B";
                            if (pr == "B" && p[4].Trim() == "")
                            {
                                r = "ERR4";
                            }
                            else
                            {
                                var d = p[2].ToUpper(CultureInfo.CurrentCulture);
                                string a = "";
                                if (d == "IT") a = "alex.demo";
                                else if (d == "OPS") a = "jordan.demo";
                                else if (d == "MKT") a = "riley.demo";
                                else if (d == "HR") a = "riley.demo";
                                if (a == "") r = "ERR3";
                                else
                                {
                                    if (pr == "H" || pr == "B") a = a + ",sam.demo";
                                    if (pr == "B") a = a + ",board";
                                    // add 15%
                                    var t = Math.Round(b * 1.15m);
                                    r = "OK;" + p[0] + ";" + pr + ";" + a + ";" + t.ToString(CultureInfo.InvariantCulture);
                                    if (f) r = r + ";MAIL";
                                }
                            }
                        }
                        else r = "ERR2";
                    }
                    else r = "ERR2";
                }
                else r = "ERR1";
            }
            else r = "ERR0";
        }
        catch (Exception)
        {
            r = "ERR";
        }
        return r;
    }
}
