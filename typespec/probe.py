"""Read a font file and return the facts a specimen is allowed to state.

Everything here comes out of the font's own tables. Where a table does not carry a value, this
module reports the absence instead of substituting a plausible number, because a specimen that
prints "x-height 1120" for a font whose OS/2 table is version 1 is printing something it made up.

Two kinds of number therefore exist side by side and are labelled as such:

  declared   read from OS/2, hhea, head, post. The designer's stated intent.
  measured   read from the glyph outlines themselves. What the shapes actually do.

They disagree in real fonts, and the disagreement is reported rather than smoothed over.
"""

from __future__ import annotations

import hashlib
from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont

# Glyphs whose outlines define the vertical measures a specimen quotes. The choice of exemplar is
# a decision, not a fact, so it is named here rather than buried in the measuring code.
MEASURE_EXEMPLARS = {
    "x_height": "x",
    "cap_height": "H",
    "ascender": "b",
    "descender": "p",
    "figure_height": "one",
}

# Vertical measure -> which edge of the exemplar's bounding box carries it.
MEASURE_EDGE = {
    "x_height": "yMax",
    "cap_height": "yMax",
    "ascender": "yMax",
    "descender": "yMin",
    "figure_height": "yMax",
}


def _name(font, *ids):
    """First non-empty Windows-Unicode name record among ``ids``."""
    table = font["name"]
    for nid in ids:
        for rec in table.names:
            if rec.nameID != nid:
                continue
            if (rec.platformID, rec.platEncID) not in ((3, 1), (3, 10), (0, 3), (0, 4), (0, 6)):
                continue
            try:
                value = rec.toUnicode()
            except UnicodeDecodeError:
                continue
            value = " ".join(value.split())
            if value:
                return value
    return None


def _cmap_codepoints(font):
    """Every codepoint the font's best unicode cmap maps to a non-.notdef glyph."""
    best = font.getBestCmap()
    return {cp for cp, gname in best.items() if gname != ".notdef"}


def to_ranges(codepoints):
    """A sorted codepoint set as inclusive ranges. Deterministic and compact."""
    out = []
    for cp in sorted(codepoints):
        if out and cp == out[-1][1] + 1:
            out[-1][1] = cp
        else:
            out.append([cp, cp])
    return [list(r) for r in out]


def _feature_records(font, tag):
    if tag not in font:
        return []
    table = font[tag].table
    if table.FeatureList is None:
        return []
    seen = {}
    for rec in table.FeatureList.FeatureRecord:
        seen.setdefault(rec.FeatureTag, set()).update(rec.Feature.LookupListIndex or [])
    return sorted((t, sorted(idx)) for t, idx in seen.items())


def _scripts(font, tag):
    if tag not in font:
        return []
    table = font[tag].table
    if table.ScriptList is None:
        return []
    return sorted({r.ScriptTag.strip() for r in table.ScriptList.ScriptRecord})


def _lookup_types(font, tag, indices):
    """Lookup types behind a feature, with extension lookups resolved to what they wrap."""
    table = font[tag].table
    types = []
    for i in indices:
        lookup = table.LookupList.Lookup[i]
        lt = lookup.LookupType
        if (tag == "GSUB" and lt == 7) or (tag == "GPOS" and lt == 9):
            for sub in lookup.SubTable:
                types.append(int(sub.ExtensionLookupType))
        else:
            types.append(int(lt))
    return sorted(set(types))


def _size_feature(font):
    """The GPOS 'size' feature's parameters, which is where optical size actually lives."""
    if "GPOS" not in font:
        return None
    table = font["GPOS"].table
    if table.FeatureList is None:
        return None
    for rec in table.FeatureList.FeatureRecord:
        if rec.FeatureTag != "size":
            continue
        params = getattr(rec.Feature, "FeatureParams", None)
        if params is None:
            continue
        design = getattr(params, "DesignSize", None)
        if design is None:
            continue
        # The file stores decipoints as uint16, and fontTools' DeciPoints converter has already
        # divided by ten by the time it reaches here. Dividing again turns a 10 pt face into a
        # 1 pt one, which is how this was caught. The raw values are kept so the independent
        # checker can compare against the bytes rather than against this reading of them.
        start = getattr(params, "RangeStart", 0)
        end = getattr(params, "RangeEnd", 0)
        return {
            "design_size": float(design),
            "subfamily_id": getattr(params, "SubfamilyID", None),
            "range_start": float(start),
            "range_end": float(end),
            "raw_decipoints": {
                "design_size": round(design * 10),
                "range_start": round(start * 10),
                "range_end": round(end * 10),
            },
        }
    return None


def _measured(glyph_set, cmap, upem):
    """Vertical measures taken from the outlines, plus the exemplar each one came from."""
    out = {}
    for measure, char in MEASURE_EXEMPLARS.items():
        cp = ord(char) if len(char) == 1 else None
        gname = cmap.get(cp) if cp is not None else (char if char in glyph_set else None)
        if gname is None or gname not in glyph_set:
            out[measure] = {"exemplar": char, "available": False, "value": None}
            continue
        pen = BoundsPen(glyph_set)
        glyph_set[gname].draw(pen)
        if pen.bounds is None:
            out[measure] = {"exemplar": char, "glyph": gname, "available": False, "value": None}
            continue
        x_min, y_min, x_max, y_max = pen.bounds
        edge = y_max if MEASURE_EDGE[measure] == "yMax" else y_min
        out[measure] = {
            "exemplar": char,
            "glyph": gname,
            "available": True,
            "value": int(round(edge)),
            "per_em": round(edge / upem, 4),
            "bbox": [int(round(v)) for v in (x_min, y_min, x_max, y_max)],
        }
    return out


def probe(path, location=None):
    """Facts about one font file. ``location`` picks an instance of a variable font."""
    font = TTFont(path, fontNumber=0, lazy=True)
    head = font["head"]
    hhea = font["hhea"]
    os2 = font.get("OS/2")
    upem = head.unitsPerEm
    cmap = font.getBestCmap()
    codepoints = _cmap_codepoints(font)
    glyph_set = font.getGlyphSet(location=location) if location else font.getGlyphSet()

    outline_format = "glyf" if "glyf" in font else ("CFF2" if "CFF2" in font else
                                                   ("CFF" if "CFF " in font else "unknown"))

    declared = {
        "units_per_em": upem,
        "os2_version": None if os2 is None else int(os2.version),
        "hhea_ascender": int(hhea.ascent),
        "hhea_descender": int(hhea.descent),
        "hhea_line_gap": int(hhea.lineGap),
    }
    # OS/2 gained sxHeight and sCapHeight at version 2. Older tables do not have the fields at
    # all, and reporting a number for them would be invention.
    for field, key in (("sxHeight", "x_height"), ("sCapHeight", "cap_height"),
                       ("sTypoAscender", "typo_ascender"), ("sTypoDescender", "typo_descender"),
                       ("sTypoLineGap", "typo_line_gap"), ("usWinAscent", "win_ascent"),
                       ("usWinDescent", "win_descent")):
        value = getattr(os2, field, None) if os2 is not None else None
        declared[key] = None if value is None else int(value)

    post = font.get("post")
    features = {}
    for tag in ("GSUB", "GPOS"):
        entries = []
        for feat_tag, indices in _feature_records(font, tag):
            entries.append({
                "tag": feat_tag,
                "lookup_count": len(indices),
                "lookup_types": _lookup_types(font, tag, indices) if indices else [],
            })
        features[tag] = entries

    fvar = None
    if "fvar" in font:
        fvar = [{
            "tag": a.axisTag,
            "min": float(a.minValue),
            "default": float(a.defaultValue),
            "max": float(a.maxValue),
            "name": _axis_name(font, a),
        } for a in font["fvar"].axes]

    facts = {
        "file_name": path.rsplit("/", 1)[-1],
        "file_sha256": _sha256(path),
        "file_bytes": _size(path),
        "family": _name(font, 16, 1),
        "subfamily": _name(font, 17, 2),
        "full_name": _name(font, 4),
        "version": _name(font, 5),
        "postscript_name": _name(font, 6),
        "embedded_license": _name(font, 13),
        "embedded_license_url": _name(font, 14),
        "outline_format": outline_format,
        "glyph_count": int(font["maxp"].numGlyphs),
        "is_fixed_pitch": bool(getattr(post, "isFixedPitch", 0)) if post else False,
        "italic_angle": float(getattr(post, "italicAngle", 0.0)) if post else 0.0,
        "instance": dict(sorted(location.items())) if location else None,
        "declared": declared,
        "measured": _measured(glyph_set, cmap, upem),
        "coverage": {
            "codepoint_count": len(codepoints),
            "ranges": to_ranges(codepoints),
        },
        "features": features,
        "scripts": {"GSUB": _scripts(font, "GSUB"), "GPOS": _scripts(font, "GPOS")},
        "has_legacy_kern_table": "kern" in font,
        "fvar": fvar,
        "size_feature": _size_feature(font),
    }
    font.close()
    return facts


def _axis_name(font, axis):
    nid = getattr(axis, "axisNameID", None)
    if nid is None:
        return None
    for rec in font["name"].names:
        if rec.nameID == nid and (rec.platformID, rec.platEncID) in ((3, 1), (3, 10)):
            try:
                return rec.toUnicode()
            except UnicodeDecodeError:
                return None
    return None


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _size(path):
    import os
    return os.path.getsize(path)
