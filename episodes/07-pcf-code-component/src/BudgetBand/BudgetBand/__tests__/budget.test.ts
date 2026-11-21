import { classify, parseAmount } from "../budget";

const enUS = { decimalSeparator: ".", groupSeparator: "," };
const ptPT = { decimalSeparator: ",", groupSeparator: "\u00a0" };

describe("parseAmount", () => {
    it.each([
        ["50000", 50000],
        ["50,000", 50000],
        ["50,000.50", 50000.5],
        ["€ 12,500", 12500],
        ["50k", 50000],
        ["1.2m", 1200000],
    ])("en-US: %s -> %d", (input, expected) => {
        expect(parseAmount(input, enUS)).toEqual({ ok: true, value: expected });
    });

    it.each([
        ["50 000", 50000],
        ["50\u00a0000,50", 50000.5],
        ["1,5k", 1500],
    ])("pt-PT: %s -> %d", (input, expected) => {
        expect(parseAmount(input, ptPT)).toEqual({ ok: true, value: expected });
    });

    it("pt-PT: a dot is not a decimal separator", () => {
        expect(parseAmount("50.000", ptPT)).toEqual({ ok: false, error: 'Use "," for decimals.' });
    });

    it("en-US: 75.000 is seventy-five, not seventy-five thousand", () => {
        expect(parseAmount("75.000", enUS)).toEqual({ ok: true, value: 75 });
    });

    it("empty input clears the value", () => {
        expect(parseAmount("   ", enUS)).toEqual({ ok: true, value: null });
    });

    it("rejects negative amounts", () => {
        expect(parseAmount("-100", enUS).ok).toBe(false);
    });

    it("rejects text", () => {
        expect(parseAmount("lots", enUS)).toEqual({ ok: false, error: "That doesn't look like an amount." });
    });
});

describe("classify", () => {
    it("empty", () => expect(classify(null, 50000).band).toBe("empty"));
    it("below the threshold is standard", () => expect(classify(49999.99, 50000).band).toBe("standard"));
    it("the threshold itself is high (same >= as the plugin)", () => expect(classify(50000, 50000).band).toBe("high"));
    it("above the approval limit", () => expect(classify(250001, 50000, 250000)).toMatchObject({ band: "overMax", ratio: 1 }));
    it("bar fills relative to the limit", () => expect(classify(125000, 50000, 250000).ratio).toBe(0.5));
});
