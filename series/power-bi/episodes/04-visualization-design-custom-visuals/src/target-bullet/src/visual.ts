"use strict";

import powerbi from "powerbi-visuals-api";
import { FormattingSettingsService } from "powerbi-visuals-utils-formattingmodel";
import "./../style/visual.less";

import VisualConstructorOptions = powerbi.extensibility.visual.VisualConstructorOptions;
import VisualUpdateOptions = powerbi.extensibility.visual.VisualUpdateOptions;
import IVisual = powerbi.extensibility.visual.IVisual;
import IVisualHost = powerbi.extensibility.visual.IVisualHost;
import IVisualEventService = powerbi.extensibility.IVisualEventService;
import ISandboxExtendedColorPalette = powerbi.extensibility.ISandboxExtendedColorPalette;

import { VisualFormattingSettingsModel } from "./settings";
import { buildItems, readCategorical } from "./model";
import { Palette, renderBullets, SvgNode } from "./view";

const SVG_NS = "http://www.w3.org/2000/svg";

/** Tree -> DOM. Text goes through textContent only: no innerHTML anywhere (certification rule). */
function toDom(node: SvgNode): Element {
    const el = document.createElementNS(SVG_NS, node.tag);
    for (const [k, v] of Object.entries(node.attrs)) el.setAttribute(k, String(v));
    if (node.text !== undefined) el.textContent = node.text;
    for (const child of node.children) el.appendChild(toDom(child));
    return el;
}

export class Visual implements IVisual {
    private host: IVisualHost;
    private events: IVisualEventService;
    private root: HTMLElement;
    private formattingSettings: VisualFormattingSettingsModel;
    private formattingSettingsService: FormattingSettingsService;

    constructor(options: VisualConstructorOptions) {
        this.host = options.host;
        this.events = options.host.eventService;
        this.root = options.element;
        this.formattingSettingsService = new FormattingSettingsService();
        this.formattingSettings = new VisualFormattingSettingsModel();
    }

    public update(options: VisualUpdateOptions): void {
        this.events.renderingStarted(options);
        try {
            const dataView = options.dataViews?.[0];
            this.formattingSettings = this.formattingSettingsService.populateFormattingSettingsModel(
                VisualFormattingSettingsModel, dataView);
            const bands = this.formattingSettings.bands;
            const tolerance = Math.min(50, Math.max(0, bands.tolerance.value)) / 100;
            const items = buildItems(readCategorical(dataView), tolerance);
            const tree = renderBullets(items, options.viewport.width, options.viewport.height, this.palette(), {
                showLabels: this.formattingSettings.labels.show.value,
                fontSize: this.formattingSettings.labels.fontSize.value,
            });
            this.root.replaceChildren(toDom(tree));
            this.events.renderingFinished(options);
        } catch (error) {
            this.events.renderingFailed(options, String(error));
            throw error;
        }
    }

    /** Theme colours normally; in Windows high contrast, only the host's foreground and background. */
    private palette(): Palette {
        const cp = this.host.colorPalette as ISandboxExtendedColorPalette;
        const bands = this.formattingSettings.bands;
        if (cp.isHighContrast) {
            const fg = cp.foreground.value;
            const bg = cp.background.value;
            return { isHighContrast: true, foreground: fg, background: bg, above: fg, near: fg, below: fg, track: bg };
        }
        return {
            isHighContrast: false,
            foreground: cp.foreground?.value ?? "#252423",
            background: cp.background?.value ?? "#FFFFFF",
            above: bands.aboveColor.value.value,
            near: bands.nearColor.value.value,
            below: bands.belowColor.value.value,
            track: "#EDEBE9",
        };
    }

    public getFormattingModel(): powerbi.visuals.FormattingModel {
        return this.formattingSettingsService.buildFormattingModel(this.formattingSettings);
    }
}
