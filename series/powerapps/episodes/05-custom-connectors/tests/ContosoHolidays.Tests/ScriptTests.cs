using System.Net;
using Newtonsoft.Json.Linq;
using Xunit;

namespace ContosoHolidays.Tests;

/// <summary>script.csx run directly, the way the platform runs it, against the recorded holiday source.</summary>
public class ScriptTests
{
    private static string[] Dates(JObject body, string list = "days") => body[list]!.Select(d => (string)d["date"]!).ToArray();

    [Fact]
    public async Task A_Lisbon_office_gets_the_13_nationwide_public_holidays_of_2026()
    {
        var source = new FakeHolidaySource();
        var (response, body) = await ScriptRunner.DaysOff(source, "fromYear=2026");

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Equal(17, FakeHolidaySource.Holidays("PublicHolidays-2026-PT.json").Count()); // what the source lists
        Assert.Equal(13, (int)body!["count"]!);
        Assert.Equal(13, body["days"]!.Count());
        Assert.Contains("2026-12-01", Dates(body));
        Assert.Contains("2026-12-08", Dates(body));
        Assert.Contains("2026-12-25", Dates(body));
        Assert.All(body["days"]!, d => Assert.Equal("National", (string)d["scope"]!));
        Assert.Equal("", (string)body["subdivision"]!);
    }

    [Fact]
    public async Task Carnival_is_listed_by_the_source_but_is_Optional_so_it_is_not_a_day_off()
    {
        var (_, body) = await ScriptRunner.DaysOff(new FakeHolidaySource(), "fromYear=2026");

        Assert.DoesNotContain("2026-02-17", Dates(body!));
        var carnival = body!["excluded"]!.Single(e => (string)e["date"]! == "2026-02-17");
        Assert.Equal("Carnival", (string)carnival["name"]!);
        Assert.Equal("Optional", (string)carnival["reason"]!);
    }

    [Fact]
    public async Task Regional_holidays_are_excluded_unless_they_belong_to_the_office_subdivision()
    {
        var (_, lisbon) = await ScriptRunner.DaysOff(new FakeHolidaySource(), "fromYear=2026");
        var (_, madeira) = await ScriptRunner.DaysOff(new FakeHolidaySource(), "fromYear=2026&subdivision=PT-30");

        Assert.Equal("Regional (PT-20)", (string)lisbon!["excluded"]!.Single(e => (string)e["date"]! == "2026-06-01")["reason"]!); // Azores Day
        Assert.DoesNotContain("2026-07-01", Dates(lisbon));                                                                   // Madeira Day

        Assert.Equal(15, (int)madeira!["count"]!);
        Assert.Equal("PT-30", (string)madeira["subdivision"]!);
        Assert.Equal("PT-30", (string)madeira["days"]!.Single(d => (string)d["date"]! == "2026-07-01")["scope"]!);
        Assert.Equal("PT-30", (string)madeira["days"]!.Single(d => (string)d["date"]! == "2026-12-26")["scope"]!);  // St. Stephen's Day
        Assert.DoesNotContain("2026-06-01", Dates(madeira));                                                          // still not Azores Day
    }

    [Fact]
    public async Task Three_years_in_one_call_are_three_backend_requests_merged_and_sorted()
    {
        var source = new FakeHolidaySource();
        var (_, body) = await ScriptRunner.DaysOff(source, "fromYear=2025&toYear=2027");

        Assert.Equal(new[]
        {
            "https://date.nager.at/api/v3/PublicHolidays/2025/PT",
            "https://date.nager.at/api/v3/PublicHolidays/2026/PT",
            "https://date.nager.at/api/v3/PublicHolidays/2027/PT",
        }, source.Requests.Select(r => r.RequestUri!.ToString()));
        Assert.All(source.Requests, r => Assert.Equal(HttpMethod.Get, r.Method));
        var dates = Dates(body!);
        Assert.Equal(dates.OrderBy(d => d, StringComparer.Ordinal), dates);
        Assert.Equal("2025-01-01", dates.First());
        Assert.Equal("2027-12-25", dates.Last());
        Assert.Equal(dates.Length, (int)body!["count"]!);
        Assert.Equal(2025, (int)body["fromYear"]!);
        Assert.Equal(2027, (int)body["toYear"]!);
    }

    [Fact]
    public async Task The_source_address_comes_from_the_incoming_request_not_from_the_code()
    {
        // Point the connector's host at your own API (same paths) and the script follows.
        var source = new FakeHolidaySource();
        await ScriptRunner.RunAsync("GetDaysOff", "https://holidays.contoso.com/hr/api/v3/DaysOff/PT?fromYear=2026", source.SendAsync);

        Assert.Equal("https://holidays.contoso.com/hr/api/v3/PublicHolidays/2026/PT", source.Requests.Single().RequestUri!.ToString());
    }

    [Fact]
    public async Task Lower_case_country_and_subdivision_are_accepted()
    {
        var source = new FakeHolidaySource();
        var (response, body) = await ScriptRunner.DaysOff(source, "fromYear=2026&subdivision=pt-30", country: "pt");

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Equal("PT", (string)body!["countryCode"]!);
        Assert.Equal("PT-30", (string)body["subdivision"]!);
        Assert.EndsWith("/2026/PT", source.Requests.Single().RequestUri!.ToString());
    }

    [Theory]
    [InlineData("PRT", "fromYear=2026", "Country must be a two-letter code")]
    [InlineData("PT", "", "From Year is required")]
    [InlineData("PT", "fromYear=26", "From Year is required")]
    [InlineData("PT", "fromYear=2O26", "From Year is required")]
    [InlineData("PT", "fromYear=2026&toYear=2025", "To Year can't be before From Year")]
    [InlineData("PT", "fromYear=2026&toYear=next", "To Year must be a year")]
    [InlineData("PT", "fromYear=2020&toYear=2025", "at most 5 years")]
    [InlineData("PT", "fromYear=2026&subdivision=ES-CT", "Subdivision must be an ISO 3166-2 code of PT")]
    [InlineData("PT", "fromYear=2026&subdivision=Madeira", "Subdivision must be an ISO 3166-2 code of PT")]
    public async Task Bad_input_is_a_400_with_a_readable_message_and_never_reaches_the_source(string country, string query, string message)
    {
        var source = new FakeHolidaySource();
        var (response, body) = await ScriptRunner.DaysOff(source, query, country);

        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.Contains(message, (string)body!["message"]!);
        Assert.Empty(source.Requests);
    }

    [Fact]
    public async Task An_unknown_country_keeps_the_404_and_passes_on_the_source_explanation()
    {
        var (response, body) = await ScriptRunner.DaysOff(new FakeHolidaySource(), "fromYear=2026", country: "XX");

        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
        Assert.Equal("The holiday source returned 404 for XX 2026: The country code provided is invalid or not recognized.", (string)body!["message"]!);
    }

    [Fact]
    public async Task A_source_error_without_json_still_gives_a_message()
    {
        var source = new FakeHolidaySource { Override = _ => new HttpResponseMessage(HttpStatusCode.ServiceUnavailable) { Content = new StringContent("upstream down") } };
        var (response, body) = await ScriptRunner.DaysOff(source, "fromYear=2026");

        Assert.Equal(HttpStatusCode.ServiceUnavailable, response.StatusCode);
        Assert.Equal("The holiday source returned 503 for PT 2026: upstream down", (string)body!["message"]!);
    }

    [Fact]
    public async Task A_failure_in_the_second_year_fails_the_whole_call_instead_of_returning_half_a_calendar()
    {
        var source = new FakeHolidaySource
        {
            Override = r => r.RequestUri!.AbsolutePath.Contains("/2027/") ? new HttpResponseMessage(HttpStatusCode.InternalServerError) : null,
        };
        var (response, _) = await ScriptRunner.DaysOff(source, "fromYear=2026&toYear=2027");

        Assert.Equal(HttpStatusCode.InternalServerError, response.StatusCode);
        Assert.Equal(2, source.Requests.Count);
    }

    [Fact]
    public async Task Two_public_holidays_on_the_same_date_are_one_day_off()
    {
        var source = new FakeHolidaySource
        {
            Override = _ => FakeHolidaySource.Json(HttpStatusCode.OK, """
                [
                  {"date":"2026-06-13","localName":"Santo António","name":"St. Anthony's Day","countryCode":"PT","global":false,"counties":["PT-11"],"types":["Public"]},
                  {"date":"2026-06-13","localName":"Dia da Cidade","name":"City Day","countryCode":"PT","global":false,"counties":["PT-11"],"types":["Public"]},
                  {"date":"2026-01-01","localName":"Ano Novo","name":"New Year's Day","countryCode":"PT","global":true,"counties":null,"types":["Public"]}
                ]
                """),
        };
        var (_, body) = await ScriptRunner.DaysOff(source, "fromYear=2026&subdivision=PT-11");

        Assert.Equal(new[] { "2026-01-01", "2026-06-13" }, Dates(body!));
        Assert.Equal("St. Anthony's Day / City Day", (string)body!["days"]![1]!["name"]!);
        Assert.Equal(2, (int)body["count"]!);
    }

    [Fact]
    public async Task The_response_is_json_and_keeps_local_names_intact()
    {
        var (response, body) = await ScriptRunner.DaysOff(new FakeHolidaySource(), "fromYear=2026");

        Assert.Equal("application/json", response.Content.Headers.ContentType!.MediaType);
        Assert.Equal("Restauração da Independência", (string)body!["days"]!.Single(d => (string)d["date"]! == "2026-12-01")["localName"]!);
    }

    [Theory]
    [InlineData("GetDaysOff", "GetDaysOff")]
    [InlineData("R2V0RGF5c09mZg==", "GetDaysOff")]      // base64 of GetDaysOff, as some regions send it (Learn)
    [InlineData("ListRows", "ListRows")]                // valid base64 too: Learn's sample would decode it to garbage
    [InlineData("Test", "Test")]
    [InlineData("", "")]
    public void The_operation_id_is_decoded_only_when_it_really_was_base64(string header, string expected) =>
        Assert.Equal(expected, Script.DecodeOperationId(header));

    [Fact]
    public void Learns_naive_decode_would_turn_a_plain_operation_id_into_garbage()
    {
        // The sample in Learn: try Convert.FromBase64String, use the result if it doesn't throw.
        var naive = System.Text.Encoding.UTF8.GetString(Convert.FromBase64String("ListRows"));
        Assert.NotEqual("ListRows", naive);
    }

    [Fact]
    public async Task A_base64_operation_id_still_reaches_GetDaysOff()
    {
        var source = new FakeHolidaySource();
        var (response, body) = await ScriptRunner.RunAsync("R2V0RGF5c09mZg==", "https://date.nager.at/api/v3/DaysOff/PT?fromYear=2026", source.SendAsync);

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Equal(13, (int)body!["count"]!);
    }

    [Fact]
    public async Task Any_other_operation_is_forwarded_unchanged()
    {
        var source = new FakeHolidaySource();
        var (response, _) = await ScriptRunner.RunAsync("ListPublicHolidays", "https://date.nager.at/api/v3/PublicHolidays/2026/PT", source.SendAsync);

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Equal("https://date.nager.at/api/v3/PublicHolidays/2026/PT", source.Requests.Single().RequestUri!.ToString());
    }
}
