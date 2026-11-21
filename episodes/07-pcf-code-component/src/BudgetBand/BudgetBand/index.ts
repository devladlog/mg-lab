import { IInputs, IOutputs } from "./generated/ManifestTypes";
import { classify, NumberFormat, parseAmount } from "./budget";

/**
 * Budget band: a currency input that understands "50k" and the user's own number format,
 * and shows which approval band the amount falls into while you type.
 * All rules live in budget.ts (unit-tested); this class only wires DOM <-> PCF.
 */
export class BudgetBand implements ComponentFramework.StandardControl<IInputs, IOutputs> {
    private context: ComponentFramework.Context<IInputs>;
    private notifyOutputChanged: () => void;
    private root: HTMLDivElement;
    private input: HTMLInputElement;
    private fill: HTMLDivElement;
    private message: HTMLDivElement;
    private value: number | null = null;
    private editing = false;

    public init(context: ComponentFramework.Context<IInputs>, notifyOutputChanged: () => void,
        state: ComponentFramework.Dictionary, container: HTMLDivElement): void {
        this.context = context;
        this.notifyOutputChanged = notifyOutputChanged;

        this.root = document.createElement("div");
        this.root.className = "bb";
        this.input = document.createElement("input");
        this.input.className = "bb-input";
        this.input.type = "text";
        this.input.setAttribute("aria-label", "Budget");
        const track = document.createElement("div");
        track.className = "bb-track";
        this.fill = document.createElement("div");
        this.fill.className = "bb-fill";
        track.appendChild(this.fill);
        this.message = document.createElement("div");
        this.message.className = "bb-msg";
        this.message.setAttribute("aria-live", "polite");
        this.root.append(this.input, track, this.message);
        container.appendChild(this.root);

        this.input.addEventListener("focus", this.onFocus);
        this.input.addEventListener("input", this.onInput);
        this.input.addEventListener("blur", this.onBlur);
    }

    public updateView(context: ComponentFramework.Context<IInputs>): void {
        this.context = context;
        this.input.disabled = context.mode.isControlDisabled;
        if (this.editing) return; // don't overwrite what the user is typing
        this.value = context.parameters.amount.raw;
        // The platform's own formatted value knows the record's currency (EUR here); formatCurrency() doesn't.
        this.input.value = this.value === null ? "" : context.parameters.amount.formatted ?? this.format(this.value);
        this.render(this.value);
    }

    public getOutputs(): IOutputs {
        return { amount: this.value ?? undefined };
    }

    public destroy(): void {
        this.input.removeEventListener("focus", this.onFocus);
        this.input.removeEventListener("input", this.onInput);
        this.input.removeEventListener("blur", this.onBlur);
    }

    private onFocus = (): void => {
        this.editing = true;
    };

    // Live feedback while typing; nothing is sent to the form until blur.
    private onInput = (): void => {
        const parsed = parseAmount(this.input.value, this.numberFormat());
        if (parsed.ok) this.render(parsed.value);
        else this.showError(parsed.error);
    };

    private onBlur = (): void => {
        this.editing = false;
        const parsed = parseAmount(this.input.value, this.numberFormat());
        if (!parsed.ok) return this.showError(parsed.error); // keep the text so the user can fix it
        this.value = parsed.value;
        this.input.value = this.value === null ? "" : this.format(this.value);
        this.render(this.value);
        this.notifyOutputChanged();
    };

    private render(value: number | null): void {
        const p = this.context.parameters;
        const result = classify(value, p.highThreshold.raw ?? 50000, p.approvalLimit.raw);
        this.root.className = `bb bb-${result.band}`;
        this.input.classList.remove("bb-invalid");
        this.fill.style.width = `${Math.round(result.ratio * 100)}%`;
        this.message.textContent = result.message;
    }

    private showError(error: string): void {
        this.root.className = "bb bb-error";
        this.input.classList.add("bb-invalid");
        this.message.textContent = error;
    }

    // Used only until the platform sends back the formatted value: no currency symbol, so never a wrong one.
    private format(value: number): string {
        return this.context.formatting.formatDecimal(value, 2);
    }

    private numberFormat(): NumberFormat {
        const info = this.context.userSettings.numberFormattingInfo;
        return { decimalSeparator: info.currencyDecimalSeparator, groupSeparator: info.currencyGroupSeparator };
    }
}
