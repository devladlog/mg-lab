// Pure logic of the Target bullet: no Power BI or DOM imports, so it runs under node --test.

export type Band = "above" | "near" | "below" | "noTarget" | "noActual";

export interface BulletInput {
    categories: string[];
    actual: (number | null)[];
    target: (number | null)[];
}

export interface BulletItem {
    category: string;
    actual: number | null;
    target: number | null;
    /** (actual - target) / target; null when there is no actual or no non-zero target (like DIVIDE -> BLANK). */
    variance: number | null;
    band: Band;
}

/** Minimal shape of a categorical DataView: just what we read, so tests don't need the Power BI API. */
export interface CategoricalLike {
    categorical?: {
        categories?: { values: unknown[] }[];
        values?: { source: { roles?: { [role: string]: boolean } }; values: unknown[] }[];
    };
}

function toNumber(v: unknown): number | null {
    return typeof v === "number" && Number.isFinite(v) ? v : null;
}

/** Reads the category, actual and target columns by role (the order of the measures in the well doesn't matter). */
export function readCategorical(dataView: CategoricalLike | undefined): BulletInput {
    const cat = dataView?.categorical;
    const categories = (cat?.categories?.[0]?.values ?? []).map((v) => (v === null || v === undefined ? "(Blank)" : String(v)));
    const byRole = (role: string) => cat?.values?.find((c) => c.source.roles?.[role]);
    const actualCol = byRole("actual");
    const targetCol = byRole("target");
    return {
        categories,
        actual: categories.map((_, i) => toNumber(actualCol?.values[i])),
        target: categories.map((_, i) => toNumber(targetCol?.values[i])),
    };
}

/** tolerance is a fraction: 0.05 = within plus or minus 5 % of the target counts as "near". */
export function classify(actual: number | null, target: number | null, tolerance: number): { variance: number | null; band: Band } {
    if (actual === null) return { variance: null, band: "noActual" };
    if (target === null || target === 0) return { variance: null, band: "noTarget" };
    const variance = (actual - target) / Math.abs(target);
    const band: Band = variance > tolerance ? "above" : variance < -tolerance ? "below" : "near";
    return { variance, band };
}

export function buildItems(input: BulletInput, tolerance: number): BulletItem[] {
    const tol = Math.max(0, tolerance);
    return input.categories.map((category, i) => {
        const actual = input.actual[i] ?? null;
        const target = input.target[i] ?? null;
        return { category, actual, target, ...classify(actual, target, tol) };
    });
}

/** Common axis for every row: the largest actual or target, plus 5 % headroom; never negative. */
export function scaleMax(items: BulletItem[]): number {
    const values = items.flatMap((it) => [it.actual ?? 0, it.target ?? 0]);
    const max = Math.max(0, ...values);
    return max === 0 ? 1 : max * 1.05;
}

/** The non-colour cue: a shape that says the same thing as the colour. */
export function marker(band: Band): string {
    switch (band) {
        case "above": return "▲"; // ▲
        case "below": return "▼"; // ▼
        case "near": return "●";  // ●
        default: return "–";      // –
    }
}

export function formatVariance(variance: number | null): string {
    if (variance === null) return "n/a";
    const pct = (variance * 100).toFixed(1);
    return variance > 0 ? `+${pct}%` : `${pct}%`;
}

export function formatAmount(value: number | null): string {
    if (value === null) return "blank";
    return new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(value);
}

export function bandWords(band: Band): string {
    switch (band) {
        case "above": return "above target";
        case "below": return "below target";
        case "near": return "on target";
        case "noTarget": return "no target";
        default: return "no actual";
    }
}

/** What a screen reader hears for one row. */
export function describe(item: BulletItem): string {
    return `${item.category}: ${formatAmount(item.actual)} against ${formatAmount(item.target)}, ` +
        `${formatVariance(item.variance)}, ${bandWords(item.band)}`;
}
