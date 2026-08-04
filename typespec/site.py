"""Assemble specimen pages.

One page per font, plus an index that sets every font side by side and carries the two studies
that only make sense across faces: declared metrics against measured ones, and the optical size
family.
"""

from __future__ import annotations

from .draw import esc

CSS = """
:root{
  --paper:#faf8f4; --ink:#1a1714; --faint:#8a8178; --rule:#ddd6cb; --accent:#8c2f16;
  --panel:#fffdfa; --measured:#8c2f16; --declared:#2a5c8a;
  --serif: ui-serif, Georgia, "Times New Roman", serif;
  --sans: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  --mono: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
}
@media (prefers-color-scheme: dark){
  :root{ --paper:#14120f; --ink:#ece6dd; --faint:#8f877d; --rule:#332e28; --accent:#e08256;
         --panel:#1b1815; --measured:#e08256; --declared:#7fb0dd; }
}
*{box-sizing:border-box}
html{ -webkit-text-size-adjust:100% }
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);
     font-size:16px;line-height:1.6;}
.wrap{max-width:960px;margin:0 auto;padding:0 24px 96px}
header.top{border-bottom:1px solid var(--rule);margin-bottom:40px;padding:56px 0 28px}
header.top h1{font-family:var(--serif);font-size:clamp(30px,6vw,52px);line-height:1.05;
  margin:0 0 10px;letter-spacing:-0.01em;font-weight:500}
header.top p{margin:0;color:var(--faint);max-width:60ch}
h2{font-family:var(--serif);font-weight:500;font-size:26px;margin:56px 0 6px;
   padding-bottom:6px;border-bottom:1px solid var(--rule)}
h3{font-family:var(--serif);font-weight:500;font-size:20px;margin:36px 0 8px}
h4{font-size:13px;letter-spacing:.09em;text-transform:uppercase;color:var(--faint);
   margin:26px 0 8px;font-weight:600}
p.lede{color:var(--ink);max-width:66ch;margin:6px 0 18px}
p.note{color:var(--faint);font-size:13.5px;margin:6px 0;max-width:72ch}
p.note.missing{color:var(--accent)}
p.status{font-family:var(--mono);font-size:12px;color:var(--faint);margin:6px 0 0}
a{color:var(--accent)}
code,.mono{font-family:var(--mono);font-size:12.5px}
.scroll{overflow-x:auto;overflow-y:hidden;max-width:100%}
svg{display:block;color:var(--ink)}
svg .tick{font-family:var(--mono);font-size:10px;fill:var(--faint)}
svg .rule{stroke-width:1}
svg .rule.measured{stroke:var(--measured);stroke-dasharray:none;opacity:.85}
svg .rule.declared{stroke:var(--declared);stroke-dasharray:4 3;opacity:.85}
svg .lbl{font-family:var(--mono);font-size:10.5px}
svg .lbl.measured{fill:var(--measured)}
svg .lbl.declared{fill:var(--declared)}
svg .cell{fill:none;stroke:var(--rule)}
svg.kernoff{opacity:.42}
svg.off{opacity:.42}
table{border-collapse:collapse;width:100%;font-size:14px;margin:8px 0 4px}
th{text-align:left;font-weight:600;font-size:11.5px;letter-spacing:.08em;
   text-transform:uppercase;color:var(--faint);border-bottom:1px solid var(--rule);padding:6px 10px 6px 0}
td{padding:6px 10px 6px 0;border-bottom:1px solid var(--rule);vertical-align:top}
td.num{font-family:var(--mono);font-size:12.5px;white-space:nowrap;text-align:right;
       padding-right:18px}
th.num{text-align:right;padding-right:18px}
td.note{color:var(--faint);font-size:12.5px}
td i{color:var(--accent);font-style:normal;font-size:12.5px}
.barcell{width:132px}
.bar{display:block;height:8px;background:var(--rule);position:relative;border-radius:1px}
.bar::after{content:"";position:absolute;inset:0 auto 0 0;width:var(--pct);
  background:var(--accent);border-radius:1px}
.pairs{display:flex;flex-wrap:wrap;gap:14px;margin:10px 0}
figure{margin:0}
.pair{border:1px solid var(--rule);background:var(--panel);padding:10px 12px 8px}
.pair .two{position:relative}
.pair .two svg{position:absolute;inset:0}
.pair .two svg.kernon{position:relative}
figcaption{font-family:var(--mono);font-size:11.5px;color:var(--faint);margin-top:6px}
.feats{display:grid;gap:14px;grid-template-columns:repeat(auto-fill,minmax(min(100%,320px),1fr))}
.feat{border:1px solid var(--rule);background:var(--panel);padding:12px 14px;min-width:0}
.feat figcaption{margin:0 0 8px;font-family:var(--sans);font-size:13px;color:var(--ink)}
.feat figcaption code{background:var(--rule);padding:1px 5px;margin-right:6px}
.feat .meta{display:block;font-family:var(--mono);font-size:11px;color:var(--faint);margin-top:3px}
.feat.skip{opacity:.75}
.feat .two svg{margin-bottom:2px}
.para{margin:18px 0}
.para .tag{font-family:var(--mono);font-size:11px;color:var(--faint)}
.stress{margin:12px 0 18px}
.cards{display:grid;gap:18px;grid-template-columns:repeat(auto-fill,minmax(min(100%,300px),1fr))}
.card{border:1px solid var(--rule);background:var(--panel);padding:16px 18px}
.card h3{margin:0 0 2px;font-size:19px}
.card .sub{color:var(--faint);font-size:12.5px;margin:0 0 10px}
.card dl{display:grid;grid-template-columns:auto 1fr;gap:2px 12px;margin:10px 0 0;font-size:12.5px}
.card dt{color:var(--faint)}
.card dd{margin:0;font-family:var(--mono);font-size:12px;text-align:right}
nav.crumb{font-size:13px;margin:22px 0 0}
footer{border-top:1px solid var(--rule);margin-top:64px;padding-top:20px;color:var(--faint);
  font-size:13px}
.legend{display:flex;gap:18px;flex-wrap:wrap;font-size:12.5px;color:var(--faint);margin:6px 0 14px}
.legend span::before{content:"";display:inline-block;width:16px;height:0;vertical-align:middle;
  margin-right:6px;border-top:2px solid currentColor}
.legend .m{color:var(--measured)} .legend .d{color:var(--declared)}
"""


def page(title, body, description=""):
    return (
        f'<meta charset="utf-8">\n'
        f'<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<title>{esc(title)}</title>\n'
        f'<meta name="description" content="{esc(description)}">\n'
        f"<style>{CSS}</style>\n"
        f'<div class="wrap">{body}</div>\n'
    )


FOOTER = (
    '<footer><p>Every number on these pages was read out of a font file by '
    '<code>typespec</code> and re-derived independently by <code>checkers/check_font_facts.py</code>, '
    'which parses the same bytes with its own sfnt reader and shares no code with the generator. '
    'No font binary is redistributed here. The glyphs are drawn as SVG outlines.</p>'
    '<p>Task ART-027 from <a href="https://github.com/JesseRWeigel/722-things-to-build">722 things '
    'to build</a>. Source: <a href="https://github.com/JesseRWeigel/type-specimen">type-specimen</a>.</p>'
    "</footer>"
)


def specimen_page(spec, entry):
    f = spec.facts
    lic = entry.get("license", "not stated")
    embedded = f.get("embedded_license")
    head = [
        '<nav class="crumb"><a href="index.html">&larr; all specimens</a></nav>',
        f'<header class="top"><h1>{esc(spec.label)}</h1>'
        f'<p>{esc(f["full_name"] or "")} &middot; version {esc(_short_version(f["version"]))} '
        f'&middot; {esc(f["outline_format"])} outlines &middot; {f["glyph_count"]} glyphs '
        f'&middot; {f["coverage"]["codepoint_count"]} codepoints</p></header>',
    ]
    body = [
        "<h2>Waterfall</h2>",
        '<p class="lede">One line, nine sizes, drawn from the outlines at each size. Nothing is '
        'scaled from a single rendering.</p>',
        spec.waterfall(),
        "<h2>Metrics</h2>",
        '<div class="legend"><span class="m">measured from the outlines</span>'
        '<span class="d">declared in OS/2</span></div>',
        spec.metric_diagram(),
        spec.metrics_table(),
        "<h2>In use</h2>",
        spec.paragraph_block(),
        "<h2>Character set</h2>",
        spec.charset(),
        "<h2>Unicode coverage</h2>",
        spec.coverage(),
        "<h2>Kerning</h2>",
        spec.kerning(),
        "<h2>OpenType features</h2>",
        spec.features(),
        "<h2>Provenance</h2>",
        f'<div class="scroll"><table><tbody>'
        f'<tr><td>file</td><td class="mono">{esc(f["file_name"])}</td></tr>'
        f'<tr><td>sha256</td><td class="mono">{esc(f["file_sha256"])}</td></tr>'
        f'<tr><td>bytes</td><td class="mono">{f["file_bytes"]}</td></tr>'
        f'<tr><td>package</td><td class="mono">{esc(entry.get("package", ""))}</td></tr>'
        f'<tr><td>license</td><td>{esc(lic)}</td></tr>'
        f'<tr><td>license text on disk</td><td class="mono">{esc(entry.get("license_file", ""))}</td></tr>'
        f'<tr><td>name ID 13</td><td>{esc(embedded) if embedded else "<i>the font carries no embedded license description</i>"}</td></tr>'
        f'</tbody></table></div>'
        f'<p class="note">This repository ships no copy of this font. The shapes above are SVG '
        f'paths generated from the outlines, which is what any printed specimen or embedded PDF '
        f'contains.</p>',
    ]
    return page(f"{spec.label} specimen", "".join(head + body) + FOOTER,
                f"Type specimen for {spec.label}, generated from the font file.")


def _short_version(version):
    if not version:
        return "unknown"
    return version.replace("Version ", "")[:40]


def index_page(cards, comparison_html, optical_html, font_count, license_rows):
    head = (
        '<header class="top"><h1>Type specimens, measured</h1>'
        '<p>Eight fonts installed on one Linux box, each read with fontTools and drawn as SVG '
        'outlines. Every metric here is labelled by where it came from: declared in the font’s '
        'OS/2 table, or measured off the glyph outlines. They disagree, and the disagreement is '
        'the interesting part.</p></header>'
    )
    body = [
        head,
        "<h2>What the fonts declare, and what they do</h2>",
        '<p class="lede">OS/2 gained <code>sxHeight</code> and <code>sCapHeight</code> at table '
        'version 2. A font with an older table does not contain those fields at all, so any '
        'specimen quoting an x-height for one has invented it. Below, an empty declared column '
        'means the field is genuinely absent.</p>',
        comparison_html,
        "<h2>Optical sizes</h2>",
        optical_html,
        "<h2>The specimens</h2>",
        '<p class="lede">Each page carries a waterfall, a metrics diagram, running text, the '
        'character set, a Unicode coverage map, the font’s own strongest kerning pairs, and a '
        'demo of every OpenType feature it declares.</p>',
        f'<div class="cards">{cards}</div>',
        "<h2>Licensing</h2>",
        '<p class="lede">No font binary is committed to this repository. The pages carry drawn '
        'outlines, which every license below permits in a document. Each font’s license text '
        'is on the machine at the path given.</p>',
        license_rows,
        FOOTER,
    ]
    return page("Type specimens, measured", "".join(body),
                f"Generated type specimens for {font_count} fonts, with declared and measured "
                f"metrics side by side.")
