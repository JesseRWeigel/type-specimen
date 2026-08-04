"""Turn a string into positioned glyphs using the font's own tables.

This is a deliberately small subset of what a real shaping engine does, and the subset is stated
rather than implied:

  * character to glyph through the best unicode cmap
  * advance widths from hmtx
  * pair kerning from GPOS PairPos (formats 1 and 2), and from the legacy kern table
  * feature application for GSUB lookup types 1 (single) and 4 (ligature) only

Anything outside that subset is reported as not applied. A feature demo that silently renders the
unfeatured string is worse than one that says it could not run, because the reader cannot tell the
difference between "this font's smcp does nothing" and "we did not try".
"""

from __future__ import annotations

# GSUB lookup types this module can apply.
APPLIABLE_GSUB = (1, 4)


def _resolve(lookup):
    """Subtables of a lookup, with an extension lookup replaced by what it wraps."""
    lt = lookup.LookupType
    if lt in (7, 9):  # GSUB extension, GPOS extension
        out = []
        for sub in lookup.SubTable:
            out.append((int(sub.ExtensionLookupType), sub.ExtSubTable))
        return out
    return [(int(lt), sub) for sub in lookup.SubTable]


def _feature_lookups(font, table_tag, feature_tag):
    if table_tag not in font:
        return []
    table = font[table_tag].table
    if table.FeatureList is None or table.LookupList is None:
        return []
    indices = set()
    for rec in table.FeatureList.FeatureRecord:
        if rec.FeatureTag == feature_tag:
            indices.update(rec.Feature.LookupListIndex or [])
    return [table.LookupList.Lookup[i] for i in sorted(indices)]


def kern_pairs(font):
    """Every horizontal pair adjustment the font declares, as {(left, right): units}.

    GPOS is read first and the legacy kern table fills in pairs GPOS does not mention, which is
    the order a shaper uses. Fonts here carry both, and they are not always the same.
    """
    pairs = {}
    for lookup in _feature_lookups(font, "GPOS", "kern"):
        for lt, sub in _resolve(lookup):
            if lt != 2:
                continue
            if sub.Format == 1:
                glyphs = sub.Coverage.glyphs
                for first, pair_set in zip(glyphs, sub.PairSet):
                    for rec in pair_set.PairValueRecord:
                        adj = getattr(rec.Value1, "XAdvance", 0) if rec.Value1 else 0
                        if adj:
                            pairs.setdefault((first, rec.SecondGlyph), int(adj))
            elif sub.Format == 2:
                class1 = sub.ClassDef1.classDefs
                class2 = sub.ClassDef2.classDefs
                covered = set(sub.Coverage.glyphs)
                by_class1 = {}
                for gname in covered:
                    by_class1.setdefault(class1.get(gname, 0), []).append(gname)
                by_class2 = {}
                for gname, cls in class2.items():
                    by_class2.setdefault(cls, []).append(gname)
                for c1, rec1 in enumerate(sub.Class1Record):
                    for c2, rec2 in enumerate(rec1.Class2Record):
                        adj = getattr(rec2.Value1, "XAdvance", 0) if rec2.Value1 else 0
                        if not adj:
                            continue
                        for left in by_class1.get(c1, ()):
                            for right in by_class2.get(c2, ()):
                                pairs.setdefault((left, right), int(adj))
    if "kern" in font:
        for sub in font["kern"].kernTables:
            if getattr(sub, "format", 0) != 0:
                continue
            for (left, right), value in sub.kernTable.items():
                if value:
                    pairs.setdefault((left, right), int(value))
    return pairs


def apply_feature(font, feature_tag, glyph_names):
    """Apply one GSUB feature to a glyph run.

    Returns (glyphs, status). ``status`` is "applied", "no-change", or a string naming the lookup
    types that were skipped. The caller must print the status, not discard it.
    """
    lookups = _feature_lookups(font, "GSUB", feature_tag)
    if not lookups:
        return list(glyph_names), "absent"
    out = list(glyph_names)
    skipped = set()
    for lookup in lookups:
        for lt, sub in _resolve(lookup):
            if lt == 1:
                mapping = sub.mapping
                out = [mapping.get(g, g) for g in out]
            elif lt == 4:
                out = _apply_ligatures(sub.ligatures, out)
            else:
                skipped.add(lt)
    if skipped:
        return out, "lookup types not implemented: " + ",".join(str(t) for t in sorted(skipped))
    return out, ("applied" if out != list(glyph_names) else "no-change")


def _apply_ligatures(ligatures, glyphs):
    out = []
    i = 0
    while i < len(glyphs):
        first = glyphs[i]
        best = None
        for lig in ligatures.get(first, ()):
            comps = list(lig.Component)
            if glyphs[i + 1:i + 1 + len(comps)] == comps:
                if best is None or len(comps) > len(best.Component):
                    best = lig
        if best is not None:
            out.append(best.LigGlyph)
            i += 1 + len(best.Component)
        else:
            out.append(first)
            i += 1
    return out


class Shaper:
    """Holds the per-font tables a run needs, so a specimen does not re-read them per string."""

    def __init__(self, font, location=None):
        self.font = font
        self.cmap = font.getBestCmap()
        self.glyph_set = font.getGlyphSet(location=location) if location else font.getGlyphSet()
        self.hmtx = font["hmtx"]
        self.upem = font["head"].unitsPerEm
        self.kern = kern_pairs(font)

    def to_glyphs(self, text):
        """Glyph names for a string, and the characters with no glyph at all."""
        names, missing = [], []
        for ch in text:
            gname = self.cmap.get(ord(ch))
            if gname is None:
                missing.append(ch)
            else:
                names.append(gname)
        return names, missing

    def advance(self, gname):
        return self.hmtx[gname][0]

    def position(self, glyph_names, kerning=True):
        """(glyph name, x offset) pairs plus the total advance, in font units."""
        out = []
        x = 0
        for i, gname in enumerate(glyph_names):
            out.append((gname, x))
            x += self.advance(gname)
            if kerning and i + 1 < len(glyph_names):
                x += self.kern.get((gname, glyph_names[i + 1]), 0)
        return out, x

    def run(self, text, kerning=True):
        glyphs, missing = self.to_glyphs(text)
        placed, width = self.position(glyphs, kerning=kerning)
        return placed, width, missing
