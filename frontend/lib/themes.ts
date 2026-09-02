export type ThemeId =
  | "classic"
  | "sage"
  | "apple"
  | "library"
  | "pastel"
  | "ice";

export type TextSizeId = "sm" | "base" | "lg";

export interface ThemePreset {
  id: ThemeId;
  label: string;
  background: string;
  text: string;
  tileBorder?: string;
}

export const THEME_PRESETS: ThemePreset[] = [
  {
    id: "classic",
    label: "Classic note",
    background: "#FAFAF7",
    text: "#3F3F46",
    tileBorder: "#e7e7e0",
  },
  {
    id: "apple",
    label: "Apple",
    background: "#F3F4F6",
    text: "#243746",
    tileBorder: "#e0e2e6",
  },
  {
    id: "sage",
    label: "Sage study",
    background: "#EEF4EF",
    text: "#415B4A",
    tileBorder: "#dae6dd",
  },
  {
    id: "library",
    label: "Library",
    background: "#F7F4EC",
    text: "#5B4A42",
    tileBorder: "#e8e2d5",
  },
  {
    id: "pastel",
    label: "Pastel",
    background: "#FAF2F3",
    text: "#554E5E",
    tileBorder: "#eddfe1",
  },
  {
    id: "ice",
    label: "Ice",
    background: "#EEF6FA",
    text: "#243746",
    tileBorder: "#d8e8f0",
  },
];

export const TEXT_SIZE_OPTIONS: {
  id: TextSizeId;
  label: string;
  previewClass: string;
}[] = [
  { id: "lg", label: "Large", previewClass: "text-lg" },
  { id: "base", label: "medium", previewClass: "text-base" },
  { id: "sm", label: "small", previewClass: "text-sm" },
];

export function getThemeById(id: ThemeId): ThemePreset {
  return THEME_PRESETS.find((t) => t.id === id) ?? THEME_PRESETS[0];
}
