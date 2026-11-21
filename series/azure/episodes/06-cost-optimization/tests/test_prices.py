import json

import pytest

from costwatch.prices import API_VERSION, HOURS_PER_MONTH, Price, PriceError, PriceQuery, RetailPrices

B1 = PriceQuery("Azure App Service", "swedencentral", "B1", "Azure App Service Basic Plan - Linux")


def page(items, next_link=None):
    return 200, {}, json.dumps({"Items": items, "NextPageLink": next_link, "Count": len(items)})


def row(price=0.0162, unit="1 Hour", meter="B1", kind="Consumption"):
    return {"retailPrice": price, "unitOfMeasure": unit, "currencyCode": "EUR", "meterName": meter, "type": kind}


def test_filter_always_asks_for_consumption_and_escapes_quotes():
    f = PriceQuery("Svc", "region", "S'1", "Prod", "Meter").odata_filter()
    assert "priceType eq 'Consumption'" in f            # never DevTest or Reservation rows
    assert "skuName eq 'S''1'" in f                # OData quote escaping
    assert f.endswith("meterName eq 'Meter'")


def test_url_pins_api_version_and_currency():
    url = RetailPrices(currency="EUR", fetch=lambda u: page([])).url(B1)
    assert f"api-version={API_VERSION}" in url and "currencyCode=EUR" in url
    assert "%24filter=" in url and "%20eq%20" in url


def test_follows_next_page_link():
    calls = []

    def fetch(url):
        calls.append(url)
        return page([row()], "https://next") if len(calls) == 1 else page([row(meter="B1 other")])

    assert len(RetailPrices(fetch=fetch).items(B1)) == 2
    assert calls[1] == "https://next"


def test_429_plain_text_waits_the_advertised_seconds_then_retries():
    answers = [(429, {"x-ms-ratelimit-retailprices-retry-after": "60"}, "Too many requests at this point. Please retry after some time."),
               page([row()])]
    slept = []
    client = RetailPrices(fetch=lambda u: answers.pop(0), sleep=slept.append)
    assert client.price(B1).unit_price == 0.0162
    assert slept == [60.0] and client.requests == 2


def test_429_forever_gives_up_with_a_clear_error():
    client = RetailPrices(fetch=lambda u: (429, {}, "Too many requests"), sleep=lambda s: None, max_retries=2)
    with pytest.raises(PriceError, match="429"):
        client.items(B1)
    assert client.requests == 3


@pytest.mark.parametrize("rows, message", [([], "got 0"), ([row(), row(meter="B1 App")], "got 2")])
def test_zero_or_several_prices_is_an_error_not_a_guess(rows, message):
    with pytest.raises(PriceError, match=message):
        RetailPrices(fetch=lambda u: page(rows)).price(B1)


def test_monthly_conversion():
    assert Price(0.01, "1 Hour", "EUR", "m").monthly(2) == pytest.approx(0.01 * HOURS_PER_MONTH * 2)
    assert Price(1.38, "1/Month", "EUR", "m").monthly() == 1.38
    with pytest.raises(PriceError, match="10K"):
        Price(0.0004, "10K", "EUR", "Disk Operations").monthly()


def test_cache_file_avoids_a_second_call(tmp_path):
    calls = []
    cache = tmp_path / "c.json"
    RetailPrices(fetch=lambda u: calls.append(u) or page([row()]), cache_file=cache).price(B1)
    RetailPrices(fetch=lambda u: calls.append(u) or page([row()]), cache_file=cache).price(B1)
    assert len(calls) == 1


def test_captured_prices_are_what_the_api_returned(prices):
    """The fixture is a cache of real answers: one Consumption row per query."""
    assert prices.price(B1) == Price(prices.price(B1).unit_price, "1 Hour", "EUR", "B1")
    assert 0.01 < prices.price(B1).unit_price < 0.03
