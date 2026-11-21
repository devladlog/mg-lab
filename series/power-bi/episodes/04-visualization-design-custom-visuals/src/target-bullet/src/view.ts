// Builds the visual as a plain tree of SVG nodes. visual.ts turns it into DOM with createElementNS and
// textContent (never innerHTML), and the tests inspect the tree directly.
import { Band, BulletItem, describe, formatVariance, marker, scaleMax } from "./model";

export interface SvgNode {
    tag: string;
    attrs: { [name: string]: string | number };
    text?: string;
    children: SvgNode[];
}

export interface Palette {
    isHighContrast: boolean;
    foreground: string;
    background: string;
    above: string;
    near: string;
    below: string;
    track: string;
}

export interface ViewOptions {
    showLabels: boolean;
    fontSize: number; // points, as the format pane gives it
}

const n = (tag: string, attrs: SvgNode["attrs"] = {}, children: SvgNode[] = [], text?: string): SvgNode =>
    ({ tag, attrs, children, ...(text === undefined ? {} : { text }) });

function bandFill(band: Band, p: Palette): string {
    if (p.isHighContrast) return p.background; // outlined shapes in high contrast (Learn guidance)
    return band === "above" ? p.above : band === "below" ? p.below : band === "near" ? p.near : p.track;
}

export function renderBullets(items: BulletItem[], width: number, height: number, p: Palette, o: ViewOptions): SvgNode {
    const fontPx = Math.round(o.fontSize * 4 / 3);
    const root = n("svg", {
        class: "targetBullet", width, height, role: "img",
        "aria-label": `Target bullet, ${items.length} ${items.length === 1 ? "category" : "categories"}`,
    });
    if (items.length === 0 || width < 80 || height < 24) {
        root.children.push(n("text", { x: 8, y: 20, fill: p.foreground, "font-size": fontPx },
            [], "Add a category, an actual and a target"));
        return root;
    }

    const labelW = Math.round(width * 0.28);
    const valueW = o.showLabels ? Math.max(64, fontPx * 5) : 0;
    const barW = Math.max(10, width - labelW - valueW - 16);
    const rowH = Math.max(fontPx + 8, Math.min(48, Math.floor(height / items.length)));
    const barH = Math.max(6, Math.round(rowH * 0.45));
    const max = scaleMax(items);
    const x = (v: number) => labelW + Math.max(0, Math.min(1, v / max)) * barW;
    const stroke: SvgNode["attrs"] = p.isHighContrast ? { stroke: p.foreground, "stroke-width": 2 } : {};

    items.forEach((it, i) => {
        const top = i * rowH;
        const mid = top + rowH / 2;
        const row = n("g", { class: `row band-${it.band}`, "aria-label": describe(it) }, [n("title", {}, [], describe(it))]);
        row.children.push(n("text", {
            x: labelW - 8, y: mid, "text-anchor": "end", "dominant-baseline": "middle",
            fill: p.foreground, "font-size": fontPx,
        }, [], it.category));
        row.children.push(n("rect", {
            class: "track", x: labelW, y: mid - barH / 2, width: barW, height: barH,
            fill: p.isHighContrast ? p.background : p.track, ...(p.isHighContrast ? { stroke: p.foreground, "stroke-width": 1, "stroke-opacity": 0.4 } : {}),
        }));
        if (it.actual !== null) {
            row.children.push(n("rect", {
                class: "actual", x: labelW, y: mid - barH / 2, width: Math.max(0, x(it.actual) - labelW), height: barH,
                fill: bandFill(it.band, p), ...stroke,
            }));
        }
        if (it.target !== null) {
            row.children.push(n("line", {
                class: "target", x1: x(it.target), x2: x(it.target), y1: mid - barH, y2: mid + barH,
                stroke: p.foreground, "stroke-width": 3,
            }));
        }
        if (o.showLabels) {
            row.children.push(n("text", {
                class: "variance", x: width - 4, y: mid, "text-anchor": "end", "dominant-baseline": "middle",
                fill: p.foreground, "font-size": fontPx,
            }, [], `${marker(it.band)} ${formatVariance(it.variance)}`));
        }
        root.children.push(row);
    });
    return root;
}
