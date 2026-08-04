"""Glyph outlines to SVG.

The specimen draws real outlines rather than setting text in a webfont. Three reasons, in order
of how much they matter:

  1. It proves the generator parsed the font. A page that says ``font-family: DejaVu Sans`` proves
     only that the reader has DejaVu Sans installed.
  2. It ships no font binary, so no redistribution question arises for any font on the machine.
  3. It renders identically for every reader, which a specimen has to do to be worth anything.

Coordinates stay in font units and are rounded to integers, so the same font always produces the
same bytes.
"""

from __future__ import annotations

import xml.sax.saxutils as saxutils
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen


def _ntos(value):
    """Integer font units. ``round`` alone can emit "-0", which differs from "0" byte for byte."""
    n = int(round(value))
    return "0" if n == 0 else str(n)


class Painter:
    """Draws runs of glyphs from one glyph set, caching each glyph's path data."""

    def __init__(self, glyph_set, upem):
        self.glyph_set = glyph_set
        self.upem = upem
        self._cache = {}

    def glyph_path(self, gname):
        """SVG path data for one glyph, in font units, y up. Empty string if the glyph is blank."""
        if gname not in self._cache:
            pen = SVGPathPen(self.glyph_set, ntos=_ntos)
            try:
                self.glyph_set[gname].draw(pen)
            except KeyError:
                self._cache[gname] = ""
                return ""
            self._cache[gname] = pen.getCommands()
        return self._cache[gname]

    def run_paths(self, placed):
        """``<path>`` elements for positioned glyphs, in font units relative to the run origin."""
        out = []
        for gname, x in placed:
            d = self.glyph_path(gname)
            if not d:
                continue
            if x:
                out.append(f'<path transform="translate({_ntos(x)} 0)" d="{d}"/>')
            else:
                out.append(f'<path d="{d}"/>')
        return out

    def combined_path(self, placed):
        """One path element for a whole run. Smaller output where per-glyph nodes are not needed."""
        pen = SVGPathPen(self.glyph_set, ntos=_ntos)
        for gname, x in placed:
            try:
                glyph = self.glyph_set[gname]
            except KeyError:
                continue
            glyph.draw(TransformPen(pen, (1, 0, 0, 1, x, 0)))
        return pen.getCommands()


def text_group(painter, placed, size_px, x_px, baseline_px, fill="currentColor", per_glyph=False):
    """A group that places a run at ``size_px`` with its baseline at ``baseline_px``."""
    scale = size_px / painter.upem
    body = painter.run_paths(placed) if per_glyph else [
        f'<path d="{painter.combined_path(placed)}"/>']
    inner = "".join(body)
    return (f'<g fill="{fill}" transform="translate({x_px:.3f} {baseline_px:.3f}) '
            f'scale({scale:.6f} {-scale:.6f})">{inner}</g>')


def svg(width, height, body, extra_class=""):
    cls = f' class="{extra_class}"' if extra_class else ""
    return (f'<svg{cls} xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.2f} '
            f'{height:.2f}" width="{width:.2f}" height="{height:.2f}" role="img">{body}</svg>')


def esc(text):
    return saxutils.escape(str(text))


def rule(x1, y1, x2, y2, cls):
    return (f'<line class="{cls}" x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}"/>')
