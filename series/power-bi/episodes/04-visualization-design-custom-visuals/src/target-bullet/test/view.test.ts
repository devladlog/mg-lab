import { test } from "node:test";
import * as assert from "node:assert/strict";
import { buildItems } from "../src/model";
import { Palette, renderBullets, SvgNode } from "../src/view";

const THEME: Palette = { isHighContrast: false, foreground: "#252423", background: "#FFFFFF",
    above: "#0B5CAD", near: "#7A6A00", below: "#B34700", track: "#EDEBE9" };
const HIGH_CONTRAST: Palette = { isHighContrast: true, foreground: "#FFFF00", background: "#000000",
    above: "#FFFF00", near: "#FFFF00", below: "#FFFF00", track: "#000000" };
const items = buildItems({ categories: ["Bikes", "Accessories", "Clothing"],
    actual: [120, 100, 50], target: [100, 101, 80] }, 0.05);

function all(node: SvgNode, pred: (n: SvgNode) => boolean): SvgNode[] {
    return [...(pred(node) ? [node] : []), ...node.children.flatMap((c) => all(c, pred))];
}
const byClass = (root: SvgNode, cls: string) => all(root, (n) => String(n.attrs.class ?? "").split(" ").includes(cls));

test("one row per category, bar coloured by band", () => {
    const svg = renderBullets(items, 400, 150, THEME, { showLabels: true, fontSize: 10 });
    assert.equal(svg.attrs.role, "img");
    assert.equal(svg.attrs["aria-label"], "Target bullet, 3 categories");
    assert.deepEqual(byClass(svg, "actual").map((r) => r.attrs.fill), ["#0B5CAD", "#7A6A00", "#B34700"]);
    assert.equal(byClass(svg, "target").length, 3);
});

test("every row has a title and an aria-label for screen readers", () => {
    const svg = renderBullets(items, 400, 150, THEME, { showLabels: true, fontSize: 10 });
    const rows = byClass(svg, "row");
    assert.equal(rows.length, 3);
    for (const row of rows) {
        assert.match(String(row.attrs["aria-label"]), /against .*target|on target/);
        assert.equal(row.children[0].tag, "title");
    }
});

test("variance labels carry a marker, so the band reads without colour", () => {
    const svg = renderBullets(items, 400, 150, THEME, { showLabels: true, fontSize: 10 });
    assert.deepEqual(byClass(svg, "variance").map((t) => t.text), ["▲ +20.0%", "● -1.0%", "▼ -37.5%"]);
});

test("high contrast: only foreground and background, outlined bars at least 2 px", () => {
    const svg = renderBullets(items, 400, 150, HIGH_CONTRAST, { showLabels: true, fontSize: 10 });
    const colours = new Set(all(svg, () => true).flatMap((n) => [n.attrs.fill, n.attrs.stroke]).filter(Boolean));
    assert.deepEqual([...colours].sort(), ["#000000", "#FFFF00"]);
    for (const bar of byClass(svg, "actual")) {
        assert.equal(bar.attrs.fill, "#000000");
        assert.equal(bar.attrs.stroke, "#FFFF00");
        assert.ok(Number(bar.attrs["stroke-width"]) >= 2);
    }
});

test("labels off: no variance text", () => {
    const svg = renderBullets(items, 400, 150, THEME, { showLabels: false, fontSize: 10 });
    assert.equal(byClass(svg, "variance").length, 0);
});

test("bars and target markers stay inside the bar area", () => {
    const big = buildItems({ categories: ["a"], actual: [1e9], target: [-5] }, 0.05);
    const svg = renderBullets(big, 300, 60, THEME, { showLabels: true, fontSize: 10 });
    const [bar] = byClass(svg, "actual");
    const [target] = byClass(svg, "target");
    assert.ok(Number(bar.attrs.x) + Number(bar.attrs.width) <= 300);
    assert.ok(Number(target.attrs.x1) >= Number(bar.attrs.x));
});

test("empty state tells the author what to add", () => {
    const svg = renderBullets([], 300, 100, THEME, { showLabels: true, fontSize: 10 });
    assert.equal(svg.children[0].text, "Add a category, an actual and a target");
});
