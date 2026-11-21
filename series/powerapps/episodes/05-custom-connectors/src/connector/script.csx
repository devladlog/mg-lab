// Custom code for the Contoso Holidays connector (runs only for the operations listed in apiProperties.json
// "scriptOperations": GetDaysOff). Learn constraints we respect here:
//  - class Script : ScriptBase with ExecuteAsync; one script file per connector; < 1 MB; must finish within 2 minutes
//  - .NET Standard 2.0 and a fixed list of namespaces (no using lines, like the pac connector init template; the tests
//    compile this file with exactly that list as usings and C# 7.3: tests/ContosoHolidays.Tests/ScriptCompileTests.cs)
//  - with all those namespaces in scope, Formatting is ambiguous (Newtonsoft.Json vs System.Xml): always qualify it
//  - send HTTP calls with this.Context.SendAsync, not your own HttpClient
public class Script : ScriptBase
{
    // A loan app needs this year and the next one; five years keeps a single call well inside the time limit.
    internal const int MaxYears = 5;

    public override async Task<HttpResponseMessage> ExecuteAsync()
    {
        string operationId = DecodeOperationId(this.Context.OperationId);
        if (operationId == "GetDaysOff")
        {
            return await this.GetDaysOffAsync().ConfigureAwait(false);
        }

        // Not in scriptOperations, so it shouldn't get here; forward it unchanged rather than fail.
        return await this.Context.SendAsync(this.Context.Request, this.CancellationToken).ConfigureAwait(false);
    }

    // Learn (known issues): "In some regions, the OperationId header returns in base64 encoded format."
    // Learn's sample decodes whenever Convert.FromBase64String succeeds, but a plain id whose length is a multiple of
    // four ("Test", "ListRows") is valid base64 too and would decode to garbage. Accept the decoded value only if it
    // looks like an operation id.
    internal static string DecodeOperationId(string value)
    {
        if (string.IsNullOrEmpty(value) || IsOperationIdLike(value) && value.Length % 4 != 0)
        {
            return value;
        }

        try
        {
            string decoded = Encoding.UTF8.GetString(Convert.FromBase64String(value));
            return IsOperationIdLike(decoded) ? decoded : value;
        }
        catch (FormatException)
        {
            return value;
        }
    }

    private static bool IsOperationIdLike(string s)
    {
        return Regex.IsMatch(s, "^[A-Z][A-Za-z0-9]{1,79}$");
    }

    private async Task<HttpResponseMessage> GetDaysOffAsync()
    {
        DaysOffRequest request;
        string error;
        if (!DaysOffRequest.TryParse(this.Context.Request.RequestUri, out request, out error))
        {
            return Message(HttpStatusCode.BadRequest, error);
        }

        var days = new List<JObject>();
        var excluded = new List<JObject>();
        for (int year = request.FromYear; year <= request.ToYear; year++)
        {
            var backend = new HttpRequestMessage(HttpMethod.Get, request.SourceUri(year));
            backend.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
            HttpResponseMessage response = await this.Context.SendAsync(backend, this.CancellationToken).ConfigureAwait(false);
            string body = response.Content == null ? "" : await response.Content.ReadAsStringAsync().ConfigureAwait(false);
            if (!response.IsSuccessStatusCode)
            {
                return Message(response.StatusCode, string.Format(
                    "The holiday source returned {0} for {1} {2}: {3}",
                    (int)response.StatusCode, request.CountryCode, year, SourceError(body)));
            }

            Classify(JArray.Parse(body), request.Subdivision, days, excluded);
        }

        JArray sortedDays = MergeSameDay(days);
        var result = new JObject
        {
            ["countryCode"] = request.CountryCode,
            ["subdivision"] = request.Subdivision ?? "",
            ["fromYear"] = request.FromYear,
            ["toYear"] = request.ToYear,
            ["count"] = sortedDays.Count,
            ["days"] = sortedDays,
            ["excluded"] = new JArray(excluded.OrderBy(h => (string)h["date"], StringComparer.Ordinal)),
        };

        var ok = new HttpResponseMessage(HttpStatusCode.OK);
        ok.Content = CreateJsonContent(result.ToString(Newtonsoft.Json.Formatting.None));
        return ok;
    }

    // A day off is a holiday of type Public that applies nationwide (global) or in the office's subdivision.
    // Everything else the source lists (Optional, Bank, School, Authorities, Observance, other regions) is excluded.
    internal static void Classify(JArray holidays, string subdivision, List<JObject> days, List<JObject> excluded)
    {
        foreach (JObject h in holidays.OfType<JObject>())
        {
            string date = (string)h["date"];
            string name = (string)h["name"];
            var types = h["types"] is JArray t ? t.Select(x => (string)x).ToList() : new List<string>();
            var counties = h["counties"] is JArray c ? c.Select(x => (string)x).ToList() : new List<string>();
            bool nationwide = h.Value<bool?>("global") ?? false;

            string reason = null;
            string scope = null;
            if (!types.Contains("Public"))
            {
                reason = types.Count > 0 ? string.Join(", ", types) : "Not public";
            }
            else if (nationwide)
            {
                scope = "National";
            }
            else if (subdivision != null && counties.Contains(subdivision))
            {
                scope = subdivision;
            }
            else
            {
                reason = "Regional (" + string.Join(", ", counties) + ")";
            }

            if (scope != null)
            {
                days.Add(new JObject
                {
                    ["date"] = date,
                    ["name"] = name,
                    ["localName"] = (string)h["localName"],
                    ["scope"] = scope,
                });
            }
            else
            {
                excluded.Add(new JObject { ["date"] = date, ["name"] = name, ["reason"] = reason });
            }
        }
    }

    // Two holidays on the same date are one day off: keep one row, join the names.
    internal static JArray MergeSameDay(List<JObject> days)
    {
        var merged = new JArray();
        foreach (var group in days.GroupBy(d => (string)d["date"]).OrderBy(g => g.Key, StringComparer.Ordinal))
        {
            JObject first = (JObject)group.First().DeepClone();
            if (group.Count() > 1)
            {
                first["name"] = string.Join(" / ", group.Select(d => (string)d["name"]).Distinct());
                first["localName"] = string.Join(" / ", group.Select(d => (string)d["localName"]).Distinct());
            }

            merged.Add(first);
        }

        return merged;
    }

    private static string SourceError(string body)
    {
        try
        {
            JObject problem = JObject.Parse(body);
            return (string)problem["detail"] ?? (string)problem["title"] ?? "no details";
        }
        catch (JsonException)
        {
            return string.IsNullOrWhiteSpace(body) ? "no details" : body.Substring(0, Math.Min(body.Length, 200));
        }
    }

    private static HttpResponseMessage Message(HttpStatusCode status, string message)
    {
        var response = new HttpResponseMessage(status);
        response.Content = CreateJsonContent(new JObject { ["message"] = message }.ToString(Newtonsoft.Json.Formatting.None));
        return response;
    }

    internal sealed class DaysOffRequest
    {
        public string CountryCode;
        public int FromYear;
        public int ToYear;
        public string Subdivision;
        public string SourceBase;   // https://date.nager.at/api/v3 : taken from the incoming URL, not hard-coded

        public Uri SourceUri(int year)
        {
            return new Uri(string.Format("{0}/PublicHolidays/{1}/{2}", this.SourceBase, year, this.CountryCode));
        }

        // The platform builds the request from the definition: host + basePath + /DaysOff/{CountryCode}?fromYear=...
        public static bool TryParse(Uri uri, out DaysOffRequest request, out string error)
        {
            request = null;
            string path = uri.AbsolutePath;
            int at = path.IndexOf("/DaysOff/", StringComparison.OrdinalIgnoreCase);
            if (at < 0)
            {
                error = "Unexpected path " + path + ".";
                return false;
            }

            string country = Uri.UnescapeDataString(path.Substring(at + "/DaysOff/".Length).Trim('/')).Trim();
            if (!Regex.IsMatch(country, "^[A-Za-z]{2}$"))
            {
                error = "Country must be a two-letter code such as PT, not '" + country + "'.";
                return false;
            }

            // HttpUtility is in System.Web, one of the supported namespaces (and part of .NET Standard 2.0).
            var query = HttpUtility.ParseQueryString(uri.Query);
            int fromYear;
            if (!TryYear(query["fromYear"], out fromYear))
            {
                error = "From Year is required and must be a year such as 2026.";
                return false;
            }

            int toYear = fromYear;
            if (!string.IsNullOrEmpty(query["toYear"]) && !TryYear(query["toYear"], out toYear))
            {
                error = "To Year must be a year such as 2027.";
                return false;
            }

            if (toYear < fromYear)
            {
                error = "To Year can't be before From Year.";
                return false;
            }

            if (toYear - fromYear + 1 > MaxYears)
            {
                error = "Ask for at most " + MaxYears + " years per call.";
                return false;
            }

            country = country.ToUpperInvariant();
            string subdivision = null;
            string value = query["subdivision"];
            if (!string.IsNullOrWhiteSpace(value))
            {
                subdivision = value.Trim().ToUpperInvariant();
                if (!Regex.IsMatch(subdivision, "^[A-Z]{2}-[A-Z0-9]{1,3}$") || !subdivision.StartsWith(country + "-", StringComparison.Ordinal))
                {
                    error = "Subdivision must be an ISO 3166-2 code of " + country + ", such as " + country + "-30.";
                    return false;
                }
            }

            request = new DaysOffRequest
            {
                CountryCode = country,
                FromYear = fromYear,
                ToYear = toYear,
                Subdivision = subdivision,
                SourceBase = uri.GetLeftPart(UriPartial.Authority) + path.Substring(0, at),
            };
            error = null;
            return true;
        }

        private static bool TryYear(string text, out int year)
        {
            // Four ASCII digits first, so int.TryParse never sees signs, spaces or culture-specific digits.
            year = 0;
            return text != null
                && Regex.IsMatch(text, "^[0-9]{4}$")
                && int.TryParse(text, out year)
                && year >= 1900 && year <= 2100;
        }
    }
}
