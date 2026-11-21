using System.Text.Json;
using Xunit;

namespace Contoso.SupportTriage.Tests;

public class LimitsRouterTests
{
    [Theory]
    [InlineData(1, 1)]
    [InlineData(1000, 1)]
    [InlineData(1001, 2)]
    [InlineData(5120, 6)]
    public void A_text_record_is_1000_characters_rounded_up(int length, int records) =>
        Assert.Equal(records, Limits.TextRecords(new string('a', length)));

    [Fact]
    public void Length_is_counted_in_text_elements_not_UTF16_units()
    {
        var family = "\U0001F468‍\U0001F469‍\U0001F467"; // one visible character, 8 UTF-16 units
        Assert.Equal(8, family.Length);
        Assert.Equal(1, Limits.LengthInTextElements(family));
    }

    [Fact]
    public void Chunk_splits_in_order_without_loss()
    {
        var chunks = Limits.Chunk(Enumerable.Range(1, 12), 5).ToList();
        Assert.Equal([5, 5, 2], chunks.Select(c => c.Count));
        Assert.Equal(Enumerable.Range(1, 12), chunks.SelectMany(c => c));
    }

    [Theory]
    [InlineData("negative", 0.95, "escalate")]
    [InlineData("negative", 0.79, "standard")]
    [InlineData("neutral", 0.1, "standard")]
    [InlineData("positive", 0.0, "standard")]
    public void Sentiment_threshold_decides_escalation(string sentiment, double negative, string route) =>
        Assert.Equal(route, Router.Route(sentiment, negative, [], "en"));

    [Fact]
    public void Card_or_bank_numbers_beat_everything_else()
    {
        Assert.Equal("security-review", Router.Route("positive", 0, ["CreditCardNumber"], "en"));
        Assert.Equal("security-review", Router.Route("negative", 1, ["InternationalBankingAccountNumber"], "es"));
    }

    [Fact]
    public void Non_english_goes_to_its_own_queue()
    {
        Assert.Equal("standard-fr", Router.Route("neutral", 0.1, ["Email"], "fr"));
        Assert.Equal("standard", Router.Route("neutral", 0.1, [], null));
    }

    [Fact]
    public void Sample_data_is_unique_and_contains_no_real_identifiers()
    {
        var path = Path.Combine(AppContext.BaseDirectory, "data", "tickets.json");
        var text = File.ReadAllText(path);
        var tickets = JsonSerializer.Deserialize<List<Ticket>>(text, new JsonSerializerOptions(JsonSerializerDefaults.Web))!;
        Assert.Equal(tickets.Count, tickets.Select(t => t.Id).Distinct().Count());
        Assert.All(tickets, t => Assert.True(Limits.LengthInTextElements(t.Text) < Limits.CharactersPerTextRecord));
        Assert.DoesNotContain("devladlog", text, StringComparison.OrdinalIgnoreCase);
    }
}
