"use strict";

import { formattingSettings } from "powerbi-visuals-utils-formattingmodel";

import FormattingSettingsCard = formattingSettings.SimpleCard;
import FormattingSettingsSlice = formattingSettings.Slice;
import FormattingSettingsModel = formattingSettings.Model;

// Defaults = the Contoso Bikes theme's good / neutral / bad (tests/test_visual_defaults.py keeps them in sync).
export const DEFAULT_ABOVE = "#0B5CAD";
export const DEFAULT_NEAR = "#7A6A00";
export const DEFAULT_BELOW = "#B34700";

class BandsCard extends FormattingSettingsCard {
    tolerance = new formattingSettings.NumUpDown({
        name: "tolerance",
        displayName: "On-target tolerance (%)",
        value: 5,
    });
    aboveColor = new formattingSettings.ColorPicker({ name: "aboveColor", displayName: "Above target", value: { value: DEFAULT_ABOVE } });
    nearColor = new formattingSettings.ColorPicker({ name: "nearColor", displayName: "On target", value: { value: DEFAULT_NEAR } });
    belowColor = new formattingSettings.ColorPicker({ name: "belowColor", displayName: "Below target", value: { value: DEFAULT_BELOW } });

    name: string = "bands";
    displayName: string = "Bands";
    slices: Array<FormattingSettingsSlice> = [this.tolerance, this.aboveColor, this.nearColor, this.belowColor];
}

class LabelsCard extends FormattingSettingsCard {
    show = new formattingSettings.ToggleSwitch({ name: "show", displayName: "Show variance", value: true });
    fontSize = new formattingSettings.NumUpDown({ name: "fontSize", displayName: "Text size", value: 10 });

    name: string = "labels";
    displayName: string = "Labels";
    slices: Array<FormattingSettingsSlice> = [this.show, this.fontSize];
}

export class VisualFormattingSettingsModel extends FormattingSettingsModel {
    bands = new BandsCard();
    labels = new LabelsCard();
    cards = [this.bands, this.labels];
}
