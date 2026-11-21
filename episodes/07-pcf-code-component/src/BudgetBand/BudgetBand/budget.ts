// Pure logic for the BudgetBand control: no DOM, no PCF context, so every rule is unit-testable.

export interface NumberFormat {
    decimalSeparator: string; // "." for en-US, "," for pt-PT
    groupSeparator: string; // "," for en-US, " " (or a no-break space) for pt-PT
}

export type ParseResult = { ok: true; value: number | null } | { ok: false; error: string };

const MULTIPLIERS: Record<string, number> = { k: 1_000, m: 1_000_000 };

/**
 * Turns what a user types into a number, using the user's own number format.
 * Accepts "50000", "50,000.50" (en-US), "50 000,50" (pt-PT), "50k", "1.2m" and an optional € or $ sign.
 * Empty input means "clear the value" (null). Negative amounts are rejected.
 */
export function parseAmount(input: string, format: NumberFormat): ParseResult {
    let text = input.trim().toLowerCase().replace(/[€$]/g, "").trim();
    if (text === "") return { ok: true, value: null };
    if (text.startsWith("-")) return { ok: false, error: "Budget can't be negative." };

    let multiplier = 1;
    const suffix = text.slice(-1);
    if (suffix in MULTIPLIERS) {
        multiplier = MULTIPLIERS[suffix];
        text = text.slice(0, -1).trim();
    }

    // Group separators go first (spaces of any kind are always grouping), then the decimal separator becomes ".".
    const group = format.groupSeparator.trim() === "" ? "" : format.groupSeparator;
    text = text.replace(/[\s\u00a0\u202f]/g, "");
    if (group) text = text.split(group).join("");
    if (format.decimalSeparator !== ".") {
        if (text.includes(".")) return { ok: false, error: `Use "${format.decimalSeparator}" for decimals.` };
        text = text.replace(format.decimalSeparator, ".");
    }

    if (!/^\d+(\.\d+)?$/.test(text)) return { ok: false, error: "That doesn't look like an amount." };
    const value = Math.round(parseFloat(text) * multiplier * 100) / 100;
    return { ok: true, value };
}

export type Band = "empty" | "standard" | "high" | "overMax";

export interface Classification {
    band: Band;
    message: string;
    ratio: number; // 0..1, how far along the bar to fill
}

/**
 * Same threshold as the server-side plugin from episode 4 (budget >= 50,000 -> High priority).
 * The control only explains what will happen; the plugin still enforces it on save.
 */
export function classify(value: number | null, highThreshold: number, max?: number | null): Classification {
    if (value === null) return { band: "empty", message: "No budget yet.", ratio: 0 };
    const top = max && max > highThreshold ? max : highThreshold * 2;
    const ratio = Math.min(value / top, 1);
    if (max && value > max) return { band: "overMax", message: "Above the approval limit: needs a board decision.", ratio: 1 };
    if (value >= highThreshold) return { band: "high", message: "High budget: priority will be set to High on save.", ratio };
    return { band: "standard", message: "Standard budget.", ratio };
}
