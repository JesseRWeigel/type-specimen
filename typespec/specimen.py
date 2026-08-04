"""Compose one font's specimen: the blocks, laid out, with the numbers that back them.

Every section here is built from `probe` facts and `shape` output. No section prints a value the
font did not supply, and where a value is absent the section says so in the place the value would
have gone.
"""

from __future__ import annotations

from fontTools.ttLib import TTFont

from . import blocks, draw, shape
from .draw import esc

CONTENT_WIDTH = 880          # px, the measure the specimen is set to
CHARSET_COLUMNS = 16
CHARSET_CELL = 52
CHARSET_SIZE = 30
KERN_PAIRS_SHOWN = 10
KERN_SAMPLE_SIZE = 64
FEATURE_SIZE = 34
DIAGRAM_SIZE = 190


class Specimen:
    def __init__(self, path, facts, location=None, label=None):
        self.path = path
        self.facts = facts
        self.font = TTFont(path, fontNumber=0, lazy=True)
        self.shaper = shape.Shaper(self.font, location=location)
        self.painter = draw.Painter(self.shaper.glyph_set, self.shaper.upem)
        self.upem = self.shaper.upem
        self.label = label or f"{facts['family']} {facts['subfamily'] or ''}".strip()

    def close(self):
        self.font.close()

    # -- helpers ------------------------------------------------------------

    def _line(self, text, size, kerning=True):
        placed, width, missing = self.shaper.run(text, kerning=kerning)
        return placed, width * size / self.upem, missing

    def _scroll(self, inner):
        return f'<div class="scroll">{inner}</div>'

    # -- sections -----------------------------------------------------------

    def waterfall(self):
        """The same line at rising sizes. The point of a waterfall is absolute size, so the SVG
        keeps its intrinsic pixel size and scrolls inside its own box on a narrow screen."""
        sizes = blocks.WATERFALL_SIZES
        pad = 16
        rows, y, max_w = [], pad, 0
        for size in sizes:
            placed, width_px, _ = self._line(blocks.WATERFALL_LINE, size)
            baseline = y + size * 0.78
            rows.append(draw.text_group(self.painter, placed, size, pad + 44, baseline))
            rows.append(f'<text class="tick" x="{pad + 36}" y="{baseline:.2f}" '
                        f'text-anchor="end">{size}</text>')
            y += size * 1.34 + 6
            max_w = max(max_w, width_px)
        height = y + pad
        width = max(CONTENT_WIDTH, max_w + pad * 2 + 48)
        return self._scroll(draw.svg(width, height, "".join(rows), "waterfall"))

    def metric_diagram(self):
        """Measured metrics drawn as rules across a real word, with declared values beside them
        where the font declares any."""
        size = DIAGRAM_SIZE
        scale = size / self.upem
        placed, width_px, _ = self._line(blocks.METRIC_WORD, size)
        pad_top, pad_bot, pad_left = 40, 44, 18
        m = self.facts["measured"]
        d = self.facts["declared"]

        lines = []
        for key in ("ascender", "cap_height", "x_height", "figure_height"):
            if m[key]["available"]:
                lines.append((key, m[key]["value"], "measured"))
        lines.append(("baseline", 0, "measured"))
        if m["descender"]["available"]:
            lines.append(("descender", m["descender"]["value"], "measured"))
        for key, label in (("x_height", "OS/2 sxHeight"), ("cap_height", "OS/2 sCapHeight"),
                           ("typo_ascender", "OS/2 sTypoAscender"),
                           ("typo_descender", "OS/2 sTypoDescender")):
            value = d.get(key if key.startswith("typo") else key)
            if value is not None:
                lines.append((label, int(value), "declared"))

        highest = max(v for _, v, _ in lines)
        lowest = min(v for _, v, _ in lines)
        height = (highest - lowest) * scale + pad_top + pad_bot
        baseline_y = pad_top + highest * scale
        text_x = pad_left + 176
        body = [draw.text_group(self.painter, placed, size, text_x, baseline_y)]
        right = text_x + width_px + 14
        width = max(CONTENT_WIDTH, right + 200)
        for label, value, kind in sorted(lines, key=lambda r: (-r[1], r[0])):
            y = baseline_y - value * scale
            body.append(f'<line class="rule {kind}" x1="{pad_left}" y1="{y:.2f}" '
                        f'x2="{right}" y2="{y:.2f}"/>')
            body.append(f'<text class="lbl {kind}" x="{right + 8}" y="{y - 3:.2f}">'
                        f'{esc(label)} {value}</text>')
        return self._scroll(draw.svg(width, height, "".join(body), "diagram"))

    def paragraph_block(self):
        """The face set as running text at three sizes, wrapped on measured width."""
        out = []
        for size in (11, 14, 19):
            lines = self._wrap(blocks.PARAGRAPH, size, CONTENT_WIDTH - 32)
            leading = size * 1.5
            body, y = [], leading
            for line in lines:
                placed, _, _ = self._line(line, size)
                body.append(draw.text_group(self.painter, placed, size, 16, y))
                y += leading
            out.append(f'<div class="para"><span class="tag">{size} px</span>'
                       + self._scroll(draw.svg(CONTENT_WIDTH, y - leading + size * 0.45,
                                               "".join(body), "text"))
                       + "</div>")
        return "".join(out)

    def _wrap(self, text, size, max_px):
        """Greedy wrap using the font's own advance widths and kerning."""
        words, lines, current = text.split(" "), [], ""
        for word in words:
            trial = word if not current else current + " " + word
            _, width_px, _ = self._line(trial, size)
            if width_px > max_px and current:
                lines.append(current)
                current = word
            else:
                current = trial
        if current:
            lines.append(current)
        return lines

    def charset(self):
        """One cell per glyph, centred on its own advance width, for the repertoire this specimen
        sets. Characters the font does not cover are listed rather than skipped."""
        present, absent = [], []
        for ch in blocks.CHARSET:
            gname = self.shaper.cmap.get(ord(ch))
            if gname is None:
                absent.append(ch)
            else:
                present.append((ch, gname))
        cols = CHARSET_COLUMNS
        rows = (len(present) + cols - 1) // cols
        width = cols * CHARSET_CELL
        height = rows * CHARSET_CELL
        scale = CHARSET_SIZE / self.upem
        body = []
        for i, (ch, gname) in enumerate(present):
            cx = (i % cols) * CHARSET_CELL
            cy = (i // cols) * CHARSET_CELL
            adv = self.shaper.advance(gname) * scale
            x = cx + (CHARSET_CELL - adv) / 2
            y = cy + CHARSET_CELL * 0.70
            body.append(f'<rect class="cell" x="{cx}" y="{cy}" width="{CHARSET_CELL}" '
                        f'height="{CHARSET_CELL}"/>')
            body.append(draw.text_group(self.painter, [(gname, 0)], CHARSET_SIZE, x, y))
        svg = self._scroll(draw.svg(width, height, "".join(body), "charset"))
        note = (f'<p class="note">{len(present)} of {len(blocks.CHARSET)} specimen characters '
                f'present.</p>')
        if absent:
            note += ('<p class="note missing">Not in this font, so not drawn: '
                     + " ".join(f"U+{ord(c):04X}" for c in absent) + "</p>")
        return svg + note

    def coverage(self):
        cov = self.facts["coverage"]
        cps = set()
        for lo, hi in cov["ranges"]:
            cps.update(range(lo, hi + 1))
        buckets = blocks.bucket(cps)
        rows = []
        for b in buckets:
            if b["size"]:
                pct = 100.0 * b["covered"] / b["size"]
                bar = f'<span class="bar" style="--pct:{pct:.1f}%"></span>'
                span = f'U+{b["start"]:04X}–U+{b["end"]:04X}'
                frac = f'{b["covered"]} / {b["size"]}'
                pct_s = f"{pct:.0f}%"
            else:
                bar, span, frac, pct_s = "", "outside the tabulated blocks", str(b["covered"]), ""
            rows.append(f'<tr><td>{esc(b["name"])}</td><td class="mono">{span}</td>'
                        f'<td class="num">{frac}</td><td class="num">{pct_s}</td>'
                        f'<td class="barcell">{bar}</td></tr>')
        return (f'<p class="lede">The cmap maps <b>{cov["codepoint_count"]}</b> codepoints to '
                f'{self.facts["glyph_count"]} glyphs.</p>'
                '<div class="scroll"><table class="cov"><thead><tr><th>block</th><th>range</th>'
                '<th>covered</th><th></th><th></th></tr></thead><tbody>'
                + "".join(rows) + "</tbody></table></div>")

    def kerning(self):
        """The font's own strongest pairs, not a list of pairs somebody expects to be kerned."""
        pairs = self.shaper.kern
        if not pairs:
            return ('<p class="note missing">This font declares no horizontal pair kerning in '
                    'GPOS or in a legacy kern table, so there is nothing to show.</p>')
        reverse = {}
        for cp, gname in self.shaper.cmap.items():
            if 0x20 <= cp < 0x2C0 or cp in (0x2018, 0x2019, 0x201C, 0x201D):
                reverse.setdefault(gname, cp)
        candidates = []
        for (left, right), value in pairs.items():
            if left in reverse and right in reverse:
                candidates.append((abs(value), value, left, right))
        candidates.sort(key=lambda r: (-r[0], r[2], r[3]))
        shown = candidates[:KERN_PAIRS_SHOWN]
        cells = []
        for _, value, left, right in shown:
            text = chr(reverse[left]) + chr(reverse[right])
            cells.append(self._pair_cell(text, [left, right], value))
        stress = []
        for line in ("AVATAR Wave Tokyo", "P.J. Yv, f) 7."):
            placed_on, w_on, _ = self._line(line, 38, kerning=True)
            placed_off, w_off, _ = self._line(line, 38, kerning=False)
            delta = w_off - w_on
            stress.append(
                '<div class="stress">'
                + self._scroll(draw.svg(max(w_on, w_off) + 20, 56,
                                        draw.text_group(self.painter, placed_off, 38, 8, 42),
                                        "kernoff"))
                + self._scroll(draw.svg(max(w_on, w_off) + 20, 56,
                                        draw.text_group(self.painter, placed_on, 38, 8, 42),
                                        "kernon"))
                + f'<p class="note">unkerned {w_off:.1f} px, kerned {w_on:.1f} px, '
                  f'{delta:+.1f} px over {len(line)} characters</p></div>')
        return (f'<p class="lede">{len(pairs)} distinct glyph pairs get a non-zero horizontal '
                f'adjustment'
                f'{", from GPOS and a legacy kern table" if self.facts["has_legacy_kern_table"] else ", from GPOS"}. '
                f'That is a count of pairs after expanding GPOS class-pair matrices, so it is '
                f'much larger than the number of records in the file. The {len(shown)} strongest '
                f'that this specimen can set are below, with the adjustment in font units.</p>'
                f'<div class="pairs">{"".join(cells)}</div>'
                f'<h4>Kerning off, then on</h4>{"".join(stress)}')

    def _pair_cell(self, text, glyph_names, value):
        size = KERN_SAMPLE_SIZE
        placed_off, w_off = self.shaper.position(glyph_names, kerning=False)
        placed_on, w_on = self.shaper.position(glyph_names, kerning=True)
        w = max(w_off, w_on) * size / self.upem + 16
        h = size * 1.25
        body = (draw.text_group(self.painter, placed_off, size, 8, size * 0.95, per_glyph=True))
        body_on = (draw.text_group(self.painter, placed_on, size, 8, size * 0.95, per_glyph=True))
        per_em = value / self.upem
        return (f'<figure class="pair"><div class="two">'
                f'{draw.svg(w, h, body, "kernoff")}{draw.svg(w, h, body_on, "kernon")}</div>'
                f'<figcaption>{esc(text)} <b>{value:+d}</b> units '
                f'({per_em * 1000:+.0f}/1000 em)</figcaption></figure>')

    def features(self):
        """One demo per declared GSUB feature. Where the demo cannot run, it says why."""
        entries = self.facts["features"]["GSUB"]
        if not entries:
            return '<p class="note missing">This font declares no GSUB features.</p>'
        out, applied, skipped = [], 0, 0
        for entry in entries:
            tag = entry["tag"]
            sample = blocks.feature_sample(tag)
            base_glyphs, _ = self.shaper.to_glyphs(sample)
            after, status = shape.apply_feature(self.font, tag, base_glyphs)
            if tag.strip() in blocks.POSITIONAL_FEATURES:
                status = "positional, needs a shaper this generator does not have"
            body = ""
            if status == "applied":
                applied += 1
                before_p, before_w = self.shaper.position(base_glyphs)
                after_p, after_w = self.shaper.position(after)
                s = FEATURE_SIZE
                w = max(before_w, after_w) * s / self.upem + 16
                body = ('<div class="two">'
                        + draw.svg(w, s * 1.5,
                                   draw.text_group(self.painter, before_p, s, 8, s * 1.1), "off")
                        + draw.svg(w, s * 1.5,
                                   draw.text_group(self.painter, after_p, s, 8, s * 1.1), "on")
                        + "</div>")
                body = self._scroll(body)
            else:
                skipped += 1
            cls = "feat ok" if status == "applied" else "feat skip"
            out.append(
                f'<figure class="{cls}"><figcaption><code>{esc(tag)}</code> '
                f'{esc(blocks.feature_name(tag.strip()))} '
                f'<span class="meta">{entry["lookup_count"]} lookup'
                f'{"" if entry["lookup_count"] == 1 else "s"}, '
                f'type{"" if len(entry["lookup_types"]) == 1 else "s"} '
                f'{",".join(str(t) for t in entry["lookup_types"]) or "none"}</span>'
                f'</figcaption>{body}'
                f'<p class="status">{esc(status)}</p></figure>')
        head = (f'<p class="lede">{len(entries)} GSUB features declared. {applied} produce a '
                f'visible substitution on this specimen’s sample text; {skipped} do not, '
                f'each with the reason stated.</p>')
        return head + '<div class="feats">' + "".join(out) + "</div>"

    def metrics_table(self):
        d, m = self.facts["declared"], self.facts["measured"]
        rows = []

        def row(label, declared, measured, note="", no_such_field=False):
            # "not in this font" means OS/2 has a slot for the value and this font's table is too
            # old to contain it. It is not the same as a metric OS/2 never carries, such as
            # figure height, which gets an em dash.
            if declared is not None:
                dv = str(declared)
            else:
                dv = "&mdash;" if no_such_field else "<i>not in this font</i>"
            mv = "&mdash;" if measured is None else str(measured)
            rows.append(f'<tr><td>{esc(label)}</td><td class="num">{dv}</td>'
                        f'<td class="num">{mv}</td><td class="note">{note}</td></tr>')

        def measured_value(key):
            return m[key]["value"] if m[key]["available"] else None

        xd, xm = d["x_height"], measured_value("x_height")
        cd, cm = d["cap_height"], measured_value("cap_height")
        note_x = _delta_note(xd, xm)
        note_c = _delta_note(cd, cm)
        row("units per em", d["units_per_em"], None, "head.unitsPerEm")
        # From here the declared column is OS/2, so a blank there is a real absence.
        row("x-height", xd, xm, note_x + " measured from the top of ‘x’")
        row("cap height", cd, cm, note_c + " measured from the top of ‘H’")
        row("ascender", d["typo_ascender"], measured_value("ascender"),
            "declared is OS/2 sTypoAscender, measured is the top of ‘b’")
        row("descender", d["typo_descender"], measured_value("descender"),
            "declared is OS/2 sTypoDescender, measured is the bottom of ‘p’")
        row("figure height", None, measured_value("figure_height"),
            "OS/2 has no field for this. Measured from the top of ‘1’, which is how lining and "
            "oldstyle figures tell themselves apart", no_such_field=True)
        row("hhea ascender", d["hhea_ascender"], None, "line box, not a letter")
        row("hhea descender", d["hhea_descender"], None, "line box, not a letter")
        row("hhea line gap", d["hhea_line_gap"], None, "")
        os2v = d["os2_version"]
        caveat = ""
        if os2v is not None and os2v < 2:
            caveat = (f'<p class="note missing">This font’s OS/2 table is version {os2v}. '
                      f'sxHeight and sCapHeight were added in version 2, so the font does not '
                      f'contain them at all and every x-height and cap height on this page was '
                      f'measured from the outlines.</p>')
        return ('<div class="scroll"><table class="metrics"><thead><tr><th>metric</th>'
                '<th>declared</th><th>measured</th><th></th></tr></thead><tbody>'
                + "".join(rows) + "</tbody></table></div>" + caveat)


def _delta_note(declared, measured):
    if declared is None or measured is None:
        return ""
    delta = measured - declared
    if delta == 0:
        return "agree."
    return f"differ by {delta:+d}."
