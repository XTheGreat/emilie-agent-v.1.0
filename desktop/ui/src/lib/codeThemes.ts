// Colour themes for code (open files, diffs, code blocks, command output), like Claude Code's Appearance > Code.
// The colours are written by hand to look like each well-known theme; they are close, not copies of the official files.
// "Claude" is Emilie's own look (the stylesheet's colours): it sets nothing, so the stylesheet applies.

export interface CodeTheme {
  id: string; name: string; dark: boolean;
  bg: string; fg: string;
  comment: string; keyword: string; string: string; number: string; fn: string; attr: string; type: string; meta: string;
}

type Row = [string, string, string, string, string, string, string, string, string, string, string, string];
const make = (dark: boolean, rows: Row[]): CodeTheme[] => rows.map(([id, name, bg, fg, comment, keyword, string, number, fn, attr, type, meta]) =>
  ({ id, name, dark, bg, fg, comment, keyword, string, number, fn, attr, type, meta }));

//        id                name                        bg         fg         comment    keyword    string     number     function   attribute  type       meta
export const LIGHT_THEMES: CodeTheme[] = make(false, [
  ["claude-light",     "Claude Light",             "#f5f4ee", "#2b2b28", "#8b8a83", "#a8467f", "#3f7d4e", "#8a4fc0", "#2f6db0", "#2a7c8a", "#7a4fb5", "#5b6a7a"],
  ["github-light",     "GitHub Light",             "#ffffff", "#24292f", "#6e7781", "#cf222e", "#0a3069", "#0550ae", "#8250df", "#0550ae", "#953800", "#116329"],
  ["github-light-hc",  "GitHub Light High Contrast", "#ffffff", "#0e1116", "#66707b", "#a0111f", "#032563", "#023b95", "#622cbc", "#023b95", "#702c00", "#024c1a"],
  ["pierre-light",     "Pierre Light",             "#ffffff", "#1a1a1c", "#84848a", "#d5313d", "#199f43", "#1ca1c7", "#7b43f8", "#d47616", "#08a8d0", "#79797f"],
  ["vscode-light",     "VS Code Light",            "#ffffff", "#000000", "#008000", "#0000ff", "#a31515", "#098658", "#795e26", "#001080", "#267f99", "#800000"],
  ["one-light",        "One Light",                "#fafafa", "#383a42", "#a0a1a7", "#a626a4", "#50a14f", "#986801", "#4078f2", "#e45649", "#c18401", "#e45649"],
  ["catppuccin-latte", "Catppuccin Latte",         "#eff1f5", "#4c4f69", "#9ca0b0", "#8839ef", "#40a02b", "#fe640b", "#1e66f5", "#df8e1d", "#df8e1d", "#d20f39"],
  ["solarized-light",  "Solarized Light",          "#fdf6e3", "#657b83", "#93a1a1", "#859900", "#2aa198", "#d33682", "#268bd2", "#b58900", "#b58900", "#cb4b16"],
  ["vitesse-light",    "Vitesse Light",            "#ffffff", "#393a34", "#a0ada0", "#1e754f", "#b56959", "#2f798a", "#59873a", "#b07d48", "#2e8f82", "#ab5959"],
  ["min-light",        "Min Light",                "#ffffff", "#24292e", "#a0a0a0", "#d32f2f", "#2b839f", "#9c5d27", "#6f42c1", "#1976d2", "#2b839f", "#1976d2"],
  ["rose-pine-dawn",   "Rosé Pine Dawn",           "#faf4ed", "#575279", "#9893a5", "#286983", "#ea9d34", "#d7827e", "#d7827e", "#907aa9", "#56949f", "#b4637a"],
  ["slack-ochin",      "Slack Ochin",              "#ffffff", "#1d1c1d", "#8a8a8a", "#c2185b", "#2e7d32", "#0b6bcb", "#7b1fa2", "#00838f", "#ef6c00", "#455a64"],
]);

export const DARK_THEMES: CodeTheme[] = make(true, [
  ["claude-dark",      "Claude Dark",              "#1f1f1f", "#d8d8d8", "#7d7c76", "#e889b8", "#a6d68a", "#c9a8f4", "#7cb7f2", "#e8c37a", "#c4a3f2", "#9fb0c0"],
  ["github-dark",      "GitHub Dark",              "#0d1117", "#c9d1d9", "#8b949e", "#ff7b72", "#a5d6ff", "#79c0ff", "#d2a8ff", "#79c0ff", "#ffa657", "#7ee787"],
  ["github-dark-dimmed", "GitHub Dark Dimmed",     "#22272e", "#adbac7", "#768390", "#f47067", "#96d0ff", "#6cb6ff", "#dcbdfb", "#6cb6ff", "#f69d50", "#8ddb8c"],
  ["github-dark-hc",   "GitHub Dark High Contrast", "#0a0c10", "#f0f3f6", "#9ea7b3", "#ff9492", "#a5d6ff", "#91cbff", "#dbb7ff", "#91cbff", "#ffb757", "#72f088"],
  ["pierre-dark",      "Pierre Dark",              "#141415", "#fbfbfb", "#84848a", "#ff678d", "#5ecc71", "#68cdf2", "#9d6afb", "#ffd452", "#08c0ef", "#ffa359"],
  ["vscode-dark",      "VS Code Dark",             "#1e1e1e", "#d4d4d4", "#6a9955", "#569cd6", "#ce9178", "#b5cea8", "#dcdcaa", "#9cdcfe", "#4ec9b0", "#569cd6"],
  ["one-dark-pro",     "One Dark Pro",             "#282c34", "#abb2bf", "#5c6370", "#c678dd", "#98c379", "#d19a66", "#61afef", "#e06c75", "#e5c07b", "#e06c75"],
  ["dracula",          "Dracula",                  "#282a36", "#f8f8f2", "#6272a4", "#ff79c6", "#f1fa8c", "#bd93f9", "#50fa7b", "#50fa7b", "#8be9fd", "#ff79c6"],
  ["dracula-soft",     "Dracula Soft",             "#282a36", "#f6f6f4", "#7b7f8b", "#f286c4", "#f6f6a4", "#bf9eee", "#62e884", "#97e1f1", "#97e1f1", "#f286c4"],
  ["catppuccin-mocha", "Catppuccin Mocha",         "#1e1e2e", "#cdd6f4", "#6c7086", "#cba6f7", "#a6e3a1", "#fab387", "#89b4fa", "#f9e2af", "#f9e2af", "#f38ba8"],
  ["nord",             "Nord",                     "#2e3440", "#d8dee9", "#616e88", "#81a1c1", "#a3be8c", "#b48ead", "#88c0d0", "#8fbcbb", "#8fbcbb", "#81a1c1"],
  ["solarized-dark",   "Solarized Dark",           "#002b36", "#839496", "#586e75", "#859900", "#2aa198", "#d33682", "#268bd2", "#b58900", "#b58900", "#cb4b16"],
  ["vitesse-dark",     "Vitesse Dark",             "#121212", "#dbd7ca", "#758575", "#4d9375", "#c98a7d", "#4c9a91", "#80a665", "#bd976a", "#5da994", "#c99076"],
  ["min-dark",         "Min Dark",                 "#1f1f1f", "#d4d4d4", "#6b737c", "#f97583", "#ffab70", "#79b8ff", "#b392f0", "#9db1c5", "#79b8ff", "#79b8ff"],
  ["monokai",          "Monokai",                  "#272822", "#f8f8f2", "#75715e", "#f92672", "#e6db74", "#ae81ff", "#a6e22e", "#a6e22e", "#66d9ef", "#f92672"],
  ["tokyo-night",      "Tokyo Night",              "#1a1b26", "#a9b1d6", "#565f89", "#bb9af7", "#9ece6a", "#ff9e64", "#7aa2f7", "#73daca", "#2ac3de", "#f7768e"],
  ["night-owl",        "Night Owl",                "#011627", "#d6deeb", "#637777", "#c792ea", "#ecc48d", "#f78c6c", "#82aaff", "#addb67", "#ffcb8b", "#7fdbca"],
  ["rose-pine",        "Rosé Pine",                "#191724", "#e0def4", "#6e6a86", "#31748f", "#f6c177", "#ebbcba", "#ebbcba", "#c4a7e7", "#9ccfd8", "#eb6f92"],
  ["ayu-dark",         "Ayu Dark",                 "#0b0e14", "#bfbdb6", "#565b66", "#ff8f40", "#aad94c", "#d2a6ff", "#ffb454", "#39bae6", "#59c2ff", "#f07178"],
  ["slack-dark",       "Slack Dark",               "#1a1d21", "#d1d2d3", "#7a7d81", "#ee6a9b", "#2bac76", "#ecb22e", "#36c5f0", "#ecb22e", "#36c5f0", "#9aa0a6"],
]);

export const FONT_SIZES = [0, 11, 12, 13, 14, 15, 16, 18];      // 0 = Emilie's default (11 px)
export const DEFAULT_CODE_PX = 11;
const DEFAULT_MONO = '"Cascadia Code", "Cascadia Mono", "JetBrains Mono", Consolas, "SF Mono", Menlo, monospace';

export const themeById = (list: CodeTheme[], id: string | undefined) => list.find((t) => t.id === id) || list[0];

/** Writes the chosen code theme, font and size onto <html> as CSS variables. Claude's own theme sets nothing. */
export function applyCodeStyle(dark: boolean, themeId: string | undefined, font: string | undefined, px: number | undefined) {
  const root = document.documentElement;
  const vars: Record<string, string> = {};
  const t = themeById(dark ? DARK_THEMES : LIGHT_THEMES, themeId);
  if (t.id !== "claude-light" && t.id !== "claude-dark") {
    Object.assign(vars, {
      "--code-bg": t.bg, "--code-bg-custom": t.bg, "--code-fg": t.fg,
      "--hl-comment": t.comment, "--hl-keyword": t.keyword, "--hl-string": t.string, "--hl-number": t.number,
      "--hl-title": t.fn, "--hl-attr": t.attr, "--hl-type": t.type, "--hl-meta": t.meta,
    });
  }
  const f = (font || "").replace(/["\\;{}]/g, "").trim();
  if (f) vars["--font-mono"] = `"${f}", ${DEFAULT_MONO}`;
  if (px && px > 0) vars["--code-size"] = px + "px";
  for (const k of ["--code-bg", "--code-bg-custom", "--code-fg", "--hl-comment", "--hl-keyword", "--hl-string", "--hl-number",
    "--hl-title", "--hl-attr", "--hl-type", "--hl-meta", "--font-mono", "--code-size"]) {
    if (k in vars) root.style.setProperty(k, vars[k]); else root.style.removeProperty(k);
  }
}
