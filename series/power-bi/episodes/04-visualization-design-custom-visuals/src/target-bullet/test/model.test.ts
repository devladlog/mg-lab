import { test } from "node:test";
import * as assert from "node:assert/strict";
import { buildItems, classify, describe, formatVariance, marker, readCategorical, scaleMax } from "../src/model";

test("classify: above, near and below with a 5 % tolerance", () => {
    assert.deepEqual(classify(110, 100, 0.05), { variance: 0.1, band: "above" });
    assert.deepEqual(classify(104, 100, 0.05).band, "near");
    assert.deepEqual(classify(95, 100, 0.05).band, "near");    // exactly -5 % is still near
    assert.deepEqual(classify(94.9, 100, 0.05).band, "below");
});

test("classify: no target or zero target gives no variance (like DIVIDE returning BLANK)", () => {
    assert.deepEqual(classify(50, null, 0.05), { variance: null, band: "noTarget" });
    assert.deepEqual(classify(50, 0, 0.05), { variance: null, band: "noTarget" });
});

test("classify: no actual is not minus 100 %", () => {
    assert.deepEqual(classify(null, 967472.88, 0.05), { variance: null, band: "noActual" });
});

test("classify: negative target uses its absolute value as the base", () => {
    assert.equal(classify(-50, -100, 0.05).band, "above");
});

test("readCategorical finds the measures by role, whatever their order in the well", () => {
    const input = readCategorical({
        categorical: {
            categories: [{ values: ["Bikes", "Clothing", null] }],
            values: [
                { source: { roles: { target: true } }, values: [100, 50, 10] },
                { source: { roles: { actual: true } }, values: [120, null, 5] },
            ],
        },
    });
    assert.deepEqual(input.categories, ["Bikes", "Clothing", "(Blank)"]);
    assert.deepEqual(input.actual, [120, null, 5]);
    assert.deepEqual(input.target, [100, 50, 10]);
});

test("readCategorical with no data view is empty, not an exception", () => {
    assert.deepEqual(readCategorical(undefined), { categories: [], actual: [], target: [] });
});

test("scaleMax: common axis with 5 % headroom; 1 when everything is blank", () => {
    const items = buildItems({ categories: ["a", "b"], actual: [80, 200], target: [100, 150] }, 0.05);
    assert.equal(scaleMax(items), 210);
    assert.equal(scaleMax(buildItems({ categories: ["a"], actual: [null], target: [null] }, 0.05)), 1);
});

test("colour is never the only cue: marker and signed percentage", () => {
    assert.equal(marker("above"), "▲");
    assert.equal(marker("below"), "▼");
    assert.equal(marker("near"), "●");
    assert.equal(formatVariance(0.08107), "+8.1%");
    assert.equal(formatVariance(-0.2198), "-22.0%");
    assert.equal(formatVariance(null), "n/a");
});

test("describe: what a screen reader hears", () => {
    // Contoso Bikes 2025: Sales Amount vs Sales PY by category (tests/test_expected.py computes the same)
    const items = buildItems({ categories: ["Accessories", "Bikes", "Clothing"],
        actual: [130320.98, 780356.80, 56795.10], target: [120256.62, 716095.45, 58577.03] }, 0.05);
    assert.deepEqual(items.map(describe), [
        "Accessories: 130,321 against 120,257, +8.4%, above target",
        "Bikes: 780,357 against 716,095, +9.0%, above target",
        "Clothing: 56,795 against 58,577, -3.0%, on target",
    ]);
    // tighter tolerance: Clothing drops below
    assert.equal(buildItems({ categories: ["Clothing"], actual: [56795.10], target: [58577.03] }, 0.02)[0].band, "below");
});
