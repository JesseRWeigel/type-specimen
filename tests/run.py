#!/usr/bin/env python3
"""The unit suite.

Every test is paired with a negative control: a deliberately wrong version of the same situation
that the test must reject. A test with no negative control has not been shown to be capable of
failing, and a suite of those passes on a broken implementation.

    python3 tests/run.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fontTools.pens.boundsPen import BoundsPen                            # noqa: E402
from fontTools.ttLib import TTFont                                        # noqa: E402

from typespec import blocks, draw, shape, specimen                        # noqa: E402
from typespec.probe import probe, to_ranges                               # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEJAVU = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
LATO = "/usr/share/fonts/truetype/lato/Lato-Regular.ttf"
LIBERATION = "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf"
LM10 = "/usr/share/texmf/fonts/opentype/public/lm/lmroman10-regular.otf"
MONO = "/usr/share/fonts/truetype/noto/NotoSansMono-Regular.ttf"

_fonts, _facts = {}, {}


def font(path):
    if path not in _fonts:
        _fonts[path] = TTFont(path, fontNumber=0, lazy=True)
    return _fonts[path]


def facts(path):
    if path not in _facts:
        _facts[path] = probe(path)
    return _facts[path]


def require_fonts():
    missing = [p for p in (DEJAVU, LATO, LIBERATION, LM10, MONO) if not os.path.exists(p)]
    if missing:
        print("These fonts are not installed, so the suite cannot run:", file=sys.stderr)
        for path in missing:
            print(f"  {path}", file=sys.stderr)
        print("\n  sudo apt-get install fonts-dejavu-core fonts-lato fonts-liberation "
              "fonts-noto-mono fonts-lmodern tex-gyre\n", file=sys.stderr)
        print("The suite is FAILING rather than skipping. Nothing below was checked.",
              file=sys.stderr)
        sys.exit(2)


# ---------------------------------------------------------------------------
# coverage

def test_ranges_round_trip():
    codepoints = {1, 2, 3, 7, 8, 100}
    assert to_ranges(codepoints) == [[1, 3], [7, 8], [100, 100]]
    flat = {cp for lo, hi in to_ranges(codepoints) for cp in range(lo, hi + 1)}
    assert flat == codepoints


def nc_ranges_round_trip():
    """A range list missing one codepoint must not round-trip."""
    codepoints = {1, 2, 3, 7, 8, 100}
    ranges = [[1, 3], [7, 8]]
    flat = {cp for lo, hi in ranges for cp in range(lo, hi + 1)}
    assert flat == codepoints


def test_coverage_matches_the_cmap():
    """The claimed ranges expand to exactly the font's own cmap, for five different fonts."""
    for path in (DEJAVU, LATO, LIBERATION, LM10, MONO):
        f = facts(path)
        claimed = {cp for lo, hi in f["coverage"]["ranges"] for cp in range(lo, hi + 1)}
        actual = {cp for cp, name in font(path).getBestCmap().items() if name != ".notdef"}
        assert claimed == actual, (
            f"{f['file_name']}: {len(claimed - actual)} claimed but absent, "
            f"{len(actual - claimed)} present but unclaimed")
        assert len(claimed) == f["coverage"]["codepoint_count"]


def nc_coverage_matches_the_cmap():
    """One invented codepoint in the claim must be caught."""
    f = facts(LIBERATION)
    claimed = {cp for lo, hi in f["coverage"]["ranges"] for cp in range(lo, hi + 1)}
    claimed.add(0x4E00)                    # a CJK ideograph Liberation Serif does not have
    actual = {cp for cp, name in font(LIBERATION).getBestCmap().items() if name != ".notdef"}
    assert claimed == actual


def test_coverage_claim_is_not_trivially_large():
    """Guards the opposite mistake: a coverage set padded to every codepoint in each range."""
    f = facts(LIBERATION)
    spanned = sum(hi - lo + 1 for lo, hi in f["coverage"]["ranges"])
    assert spanned == f["coverage"]["codepoint_count"]
    # And the font really is sparse, so this is a live constraint rather than a tautology.
    lo = f["coverage"]["ranges"][0][0]
    hi = f["coverage"]["ranges"][-1][1]
    assert f["coverage"]["codepoint_count"] < (hi - lo + 1) / 2


def nc_coverage_claim_is_not_trivially_large():
    """A claim of one solid range from first to last codepoint must be rejected."""
    f = facts(LIBERATION)
    lo = f["coverage"]["ranges"][0][0]
    hi = f["coverage"]["ranges"][-1][1]
    padded = [[lo, hi]]
    spanned = sum(b - a + 1 for a, b in padded)
    assert spanned == f["coverage"]["codepoint_count"]


def test_block_table_is_disjoint_and_ascending():
    previous_end = -1
    for start, end, name in blocks.BLOCKS:
        assert start <= end, f"{name} starts after it ends"
        assert start > previous_end, f"{name} overlaps the block before it"
        previous_end = end
    assert len({name for _, _, name in blocks.BLOCKS}) == len(blocks.BLOCKS)


def nc_block_table_is_disjoint_and_ascending():
    """The same validator must reject an overlapping table."""
    table = [(0x0000, 0x00FF, "A"), (0x00F0, 0x01FF, "B")]
    previous_end = -1
    for start, end, name in table:
        assert start <= end
        assert start > previous_end, f"{name} overlaps the block before it"
        previous_end = end


def test_bucket_counts_every_codepoint_once():
    for path in (DEJAVU, LATO, MONO):
        f = facts(path)
        cps = {cp for lo, hi in f["coverage"]["ranges"] for cp in range(lo, hi + 1)}
        total = sum(b["covered"] for b in blocks.bucket(cps))
        assert total == len(cps), f"{f['file_name']}: bucketed {total} of {len(cps)}"
        for b in blocks.bucket(cps):
            if b["size"]:
                assert b["covered"] <= b["size"], f"{b['name']} claims more than it can hold"


def nc_bucket_counts_every_codepoint_once():
    """A block claiming more covered codepoints than it contains must be caught."""
    fake = [{"name": "Basic Latin", "covered": 200, "size": 128}]
    for b in fake:
        assert b["covered"] <= b["size"], f"{b['name']} claims more than it can hold"


# ---------------------------------------------------------------------------
# metrics

def test_measured_metrics_come_from_the_named_exemplar():
    """The measured x-height is the top of 'x', not of some other glyph."""
    for path in (DEJAVU, LATO, LM10):
        f = facts(path)
        ttf = font(path)
        glyph_set = ttf.getGlyphSet()
        cmap = ttf.getBestCmap()
        for measure, char in (("x_height", "x"), ("cap_height", "H"), ("descender", "p")):
            pen = BoundsPen(glyph_set)
            glyph_set[cmap[ord(char)]].draw(pen)
            edge = pen.bounds[1] if measure == "descender" else pen.bounds[3]
            assert f["measured"][measure]["value"] == int(round(edge)), (
                f"{f['file_name']} {measure}")
            assert f["measured"][measure]["exemplar"] == char


def nc_measured_metrics_come_from_the_named_exemplar():
    """Measuring the wrong letter must fail the same assertion."""
    f = facts(LATO)
    ttf = font(LATO)
    glyph_set = ttf.getGlyphSet()
    pen = BoundsPen(glyph_set)
    glyph_set[ttf.getBestCmap()[ord("X")]].draw(pen)     # cap X, not lowercase x
    assert f["measured"]["x_height"]["value"] == int(round(pen.bounds[3]))


def test_absent_os2_fields_are_reported_absent():
    """DejaVu's OS/2 is version 1, so sxHeight and sCapHeight are not in the file."""
    d = facts(DEJAVU)["declared"]
    assert d["os2_version"] < 2
    assert d["x_height"] is None and d["cap_height"] is None
    # A font that does have them must not report None, or the rule above is vacuous.
    lato = facts(LATO)["declared"]
    assert lato["os2_version"] >= 2
    assert lato["x_height"] is not None and lato["cap_height"] is not None


def nc_absent_os2_fields_are_reported_absent():
    """A generator that filled the gap with the measured value must be caught."""
    d = dict(facts(DEJAVU)["declared"])
    d["x_height"] = facts(DEJAVU)["measured"]["x_height"]["value"]      # the invented value
    assert d["x_height"] is None


def test_declared_and_measured_are_separate_numbers():
    """Where both exist they may agree, and the specimen must still label which is which."""
    agree = disagree = 0
    for path in (LATO, LIBERATION, LM10, MONO):
        f = facts(path)
        declared = f["declared"]["x_height"]
        measured = f["measured"]["x_height"]["value"]
        assert declared is not None
        if declared == measured:
            agree += 1
        else:
            disagree += 1
    assert agree + disagree == 4
    note_same = specimen._delta_note(100, 100)
    note_diff = specimen._delta_note(100, 112)
    assert note_same == "agree." and note_diff == "differ by +12."
    assert specimen._delta_note(None, 112) == ""


def nc_declared_and_measured_are_separate_numbers():
    """A note generator that reported agreement regardless must be caught."""
    def always_agree(declared, measured):
        return "agree."
    assert always_agree(100, 112) == "differ by +12."


def test_size_feature_is_not_divided_twice():
    """DesignSize is stored as decipoints and fontTools already converts it."""
    sf = facts(LM10)["size_feature"]
    assert sf is not None
    assert sf["design_size"] == 10.0, sf
    assert sf["raw_decipoints"]["design_size"] == 100
    assert sf["raw_decipoints"]["design_size"] == round(sf["design_size"] * 10)


def nc_size_feature_is_not_divided_twice():
    """The bug this test was written for: dividing by ten a second time."""
    sf = dict(facts(LM10)["size_feature"])
    sf["design_size"] = sf["design_size"] / 10.0
    assert sf["design_size"] == 10.0


def test_fonts_without_a_size_feature_report_none():
    assert facts(DEJAVU)["size_feature"] is None
    assert facts(LM10)["size_feature"] is not None


def nc_fonts_without_a_size_feature_report_none():
    assert facts(LM10)["size_feature"] is None


# ---------------------------------------------------------------------------
# shaping

def test_kerning_actually_moves_glyphs():
    """For a pair the font itself declares, kerned and unkerned widths must differ by the
    declared amount, exactly."""
    for path in (LIBERATION, LATO, LM10):
        shaper = shape.Shaper(font(path))
        assert shaper.kern, f"{path} has no kern pairs, so this test proves nothing"
        (left, right), value = max(shaper.kern.items(), key=lambda kv: abs(kv[1]))
        _, width_on = shaper.position([left, right], kerning=True)
        _, width_off = shaper.position([left, right], kerning=False)
        assert width_on - width_off == value, (path, left, right, value)
        assert value != 0


def nc_kerning_actually_moves_glyphs():
    """A shaper with kerning dropped must fail the same assertion."""
    shaper = shape.Shaper(font(LIBERATION))
    (left, right), value = max(shaper.kern.items(), key=lambda kv: abs(kv[1]))
    shaper.kern = {}
    _, width_on = shaper.position([left, right], kerning=True)
    _, width_off = shaper.position([left, right], kerning=False)
    assert width_on - width_off == value


def test_a_font_with_no_kerning_says_so():
    shaper = shape.Shaper(font(MONO))
    assert shaper.kern == {}
    html = specimen.Specimen(MONO, facts(MONO)).kerning()
    assert "declares no horizontal pair kerning" in html
    assert "strongest" not in html


def nc_a_font_with_no_kerning_says_so():
    """A font that does kern must not produce the no-kerning notice."""
    html = specimen.Specimen(LIBERATION, facts(LIBERATION)).kerning()
    assert "declares no horizontal pair kerning" in html


def test_advances_come_from_hmtx():
    shaper = shape.Shaper(font(LATO))
    hmtx = font(LATO)["hmtx"]
    glyphs, _ = shaper.to_glyphs("Hamburg")
    _, total = shaper.position(glyphs, kerning=False)
    assert total == sum(hmtx[g][0] for g in glyphs)


def nc_advances_come_from_hmtx():
    """A run positioned on a constant advance must not match hmtx."""
    shaper = shape.Shaper(font(LATO))
    hmtx = font(LATO)["hmtx"]
    glyphs, _ = shaper.to_glyphs("Hamburg")
    total = 500 * len(glyphs)
    assert total == sum(hmtx[g][0] for g in glyphs)


def test_monospace_advances_are_all_equal():
    shaper = shape.Shaper(font(MONO))
    glyphs, _ = shaper.to_glyphs("iWm.1")
    widths = {shaper.advance(g) for g in glyphs}
    assert len(widths) == 1, widths
    proportional = shape.Shaper(font(LATO))
    glyphs, _ = proportional.to_glyphs("iWm.1")
    assert len({proportional.advance(g) for g in glyphs}) > 1


def nc_monospace_advances_are_all_equal():
    proportional = shape.Shaper(font(LATO))
    glyphs, _ = proportional.to_glyphs("iWm.1")
    assert len({proportional.advance(g) for g in glyphs}) == 1


def test_ligature_substitution_really_substitutes():
    shaper = shape.Shaper(font(LATO))
    glyphs, _ = shaper.to_glyphs("office")
    after, status = shape.apply_feature(font(LATO), "liga", glyphs)
    assert status == "applied"
    assert len(after) < len(glyphs), (glyphs, after)


def nc_ligature_substitution_really_substitutes():
    """An unchanged run must not be reported as applied."""
    shaper = shape.Shaper(font(LATO))
    glyphs, _ = shaper.to_glyphs("xyz")
    after, status = shape.apply_feature(font(LATO), "liga", glyphs)
    assert status == "applied" and len(after) < len(glyphs)


def test_absent_feature_is_named_absent_not_silently_unchanged():
    shaper = shape.Shaper(font(MONO))
    glyphs, _ = shaper.to_glyphs("office")
    after, status = shape.apply_feature(font(MONO), "dlig", glyphs)
    assert status == "absent"
    assert after == glyphs
    # And a feature the font does declare must not be called absent.
    _, present = shape.apply_feature(font(MONO), "smcp", glyphs)
    assert present != "absent"


def nc_absent_feature_is_named_absent_not_silently_unchanged():
    shaper = shape.Shaper(font(MONO))
    glyphs, _ = shaper.to_glyphs("office")
    _, status = shape.apply_feature(font(MONO), "smcp", glyphs)
    assert status == "absent"


def test_unimplemented_lookup_types_are_reported():
    """Every status string is one of the four the module documents, and any lookup type outside
    types 1 and 4 produces the naming status rather than a quiet pass."""
    allowed_prefixes = ("applied", "no-change", "absent", "lookup types not implemented:")
    seen_unimplemented = False
    for path in (DEJAVU, LATO, LM10, LIBERATION, MONO):
        f = font(path)
        shaper = shape.Shaper(f)
        for entry in facts(path)["features"]["GSUB"]:
            glyphs, _ = shaper.to_glyphs(blocks.feature_sample(entry["tag"]))
            _, status = shape.apply_feature(f, entry["tag"], glyphs)
            assert status.startswith(allowed_prefixes), (path, entry["tag"], status)
            if status.startswith("lookup types not implemented"):
                seen_unimplemented = True
                for part in status.split(":", 1)[1].split(","):
                    assert int(part) not in shape.APPLIABLE_GSUB
    assert seen_unimplemented, ("no font here exercises an unimplemented lookup type, so this "
                                "test proves nothing")


def nc_unimplemented_lookup_types_are_reported():
    """A status of 'applied' for a type the module cannot apply must be caught."""
    status = "applied"
    assert status.startswith("lookup types not implemented:")


# ---------------------------------------------------------------------------
# drawing

def test_glyph_paths_are_deterministic_and_non_empty():
    for path in (DEJAVU, LM10):
        ttf = font(path)
        shaper = shape.Shaper(ttf)
        one = draw.Painter(ttf.getGlyphSet(), shaper.upem)
        two = draw.Painter(ttf.getGlyphSet(), shaper.upem)
        for char in "HxOgQ8":
            gname = shaper.cmap[ord(char)]
            first, second = one.glyph_path(gname), two.glyph_path(gname)
            assert first == second
            assert len(first) > 40, (path, char, first)
            assert first.startswith("M")


def nc_glyph_paths_are_deterministic_and_non_empty():
    """An empty path must not satisfy the non-empty assertion."""
    first = ""
    assert len(first) > 40 and first.startswith("M")


def test_path_numbers_are_integers_with_no_negative_zero():
    ttf = font(LM10)
    shaper = shape.Shaper(ttf)
    painter = draw.Painter(ttf.getGlyphSet(), shaper.upem)
    import re
    seen = 0
    for char in "HxOgQ8eas":
        d = painter.glyph_path(shaper.cmap[ord(char)])
        # SVGPathPen emits M L C Q H V Z. Everything between commands must be an integer.
        for token in re.split(r"[MLCQHVZmlcqhvz]", d):
            for number in token.split():
                assert number != "-0"
                int(number)                 # raises if a float sneaked in
                seen += 1
    assert seen > 200, seen


def nc_path_numbers_are_integers_with_no_negative_zero():
    for token in ("12", "-0", "7"):
        assert token != "-0"


def test_space_glyph_draws_nothing_but_still_advances():
    shaper = shape.Shaper(font(LATO))
    painter = draw.Painter(shaper.glyph_set, shaper.upem)
    gname = shaper.cmap[ord(" ")]
    assert painter.glyph_path(gname) == ""
    assert shaper.advance(gname) > 0


def nc_space_glyph_draws_nothing_but_still_advances():
    shaper = shape.Shaper(font(LATO))
    painter = draw.Painter(shaper.glyph_set, shaper.upem)
    assert painter.glyph_path(shaper.cmap[ord("H")]) == ""


def test_wrapping_uses_the_font_own_widths():
    spec = specimen.Specimen(LATO, facts(LATO))
    lines = spec._wrap(blocks.PARAGRAPH, 14, 400)
    assert len(lines) > 1
    for line in lines:
        _, width, _ = spec._line(line, 14)
        assert width <= 400 or " " not in line, (line, width)
    assert " ".join(lines) == blocks.PARAGRAPH


def nc_wrapping_uses_the_font_own_widths():
    """Lines wider than the measure must be caught."""
    spec = specimen.Specimen(LATO, facts(LATO))
    lines = spec._wrap(blocks.PARAGRAPH, 14, 4000)
    for line in lines:
        _, width, _ = spec._line(line, 14)
        assert width <= 400 or " " not in line


# ---------------------------------------------------------------------------
# the rendered page

def test_feature_demo_shows_two_different_runs():
    """An applied feature must render a before that differs from the after. A demo that draws the
    substituted run twice looks convincing and shows nothing."""
    import re
    html = specimen.Specimen(LATO, facts(LATO)).features()
    applied = re.findall(r'<figure class="feat ok">.*?</figure>', html, re.S)
    assert len(applied) >= 3, f"only {len(applied)} applied features to inspect"
    for figure in applied:
        paths = re.findall(r'<path d="([^"]+)"', figure)
        assert len(paths) == 2, f"expected a before and an after, got {len(paths)}"
        assert paths[0] != paths[1], "the before and after runs are identical"


def nc_feature_demo_shows_two_different_runs():
    """Two identical runs must be rejected."""
    paths = ["M0 0L1 1Z", "M0 0L1 1Z"]
    assert paths[0] != paths[1], "the before and after runs are identical"


def test_charset_only_draws_characters_the_font_has():
    html = specimen.Specimen(LM10, facts(LM10)).charset()
    lm_cmap = font(LM10).getBestCmap()
    absent = [c for c in blocks.CHARSET if ord(c) not in lm_cmap]
    assert absent, "this font covers the whole specimen charset, so the notice is untestable"
    assert "Not in this font, so not drawn" in html
    for char in absent:
        assert f"U+{ord(char):04X}" in html
    present = [c for c in blocks.CHARSET if ord(c) in lm_cmap]
    assert f"{len(present)} of {len(blocks.CHARSET)}" in html


def nc_charset_only_draws_characters_the_font_has():
    """A font covering everything must not produce the missing-character notice."""
    html = specimen.Specimen(DEJAVU, facts(DEJAVU)).charset()
    assert "Not in this font, so not drawn" in html


def test_metrics_table_prints_absent_not_a_number():
    html = specimen.Specimen(DEJAVU, facts(DEJAVU)).metrics_table()
    assert "not in this font" in html
    assert "OS/2 table is version 1" in html
    measured = facts(DEJAVU)["measured"]["x_height"]["value"]
    assert str(measured) in html
    lato_html = specimen.Specimen(LATO, facts(LATO)).metrics_table()
    assert "not in this font" not in lato_html
    assert "OS/2 table is version" not in lato_html


def nc_metrics_table_prints_absent_not_a_number():
    html = specimen.Specimen(LATO, facts(LATO)).metrics_table()
    assert "not in this font" in html


def test_built_pages_carry_the_measured_numbers():
    index = read(os.path.join(REPO, "docs", "index.html"))
    assert index, "docs/index.html is missing, run: python3 -m typespec.cli build"
    import json
    with open(os.path.join(REPO, "out", "_index.json"), encoding="utf-8") as fh:
        summary = json.load(fh)
    for entry in summary["fonts"]:
        page = read(os.path.join(REPO, "docs", entry["slug"] + ".html"))
        assert page, f"docs/{entry['slug']}.html is missing"
        assert str(entry["x_height_measured"]) in page
        assert str(entry["codepoint_count"]) in page
        assert str(entry["x_height_measured"]) in index
    for member in summary["optical"]["members"]:
        assert f"{member['design_size']:g}" in index


def nc_built_pages_carry_the_measured_numbers():
    """A number no font on this page measured must not be found in it."""
    index = read(os.path.join(REPO, "docs", "index.html"))
    assert "999999" in index


def test_pages_have_no_absolute_home_path():
    hits = []
    for name in sorted(os.listdir(os.path.join(REPO, "docs"))):
        text = read(os.path.join(REPO, "docs", name))
        for needle in _HOME_NEEDLES:
            if needle in text:
                hits.append(f"{name} contains {needle}")
    assert not hits, hits
    # The detector must be able to see one, or its silence means nothing.
    assert _home_hits("a path like /" + "home/somebody/x") == [_HOME_NEEDLES[0]]


def nc_pages_have_no_absolute_home_path():
    assert _home_hits("a path like /" + "home/somebody/x") == []


# Assembled from fragments rather than written whole, so this file does not itself contain a
# complete home-path pattern for the hygiene scan in verify.sh to trip over.
_HOME_NEEDLES = ("/" + "home/", "/" + "Users/", "C:" + "\\Users")


def _home_hits(text):
    return [n for n in _HOME_NEEDLES if n in text]


def read(path):
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as fh:
        return fh.read()


# ---------------------------------------------------------------------------

def main():
    require_fonts()
    names = [n for n in globals() if n.startswith("test_")]
    names.sort(key=lambda n: list(globals()).index(n))
    passed = failed = 0
    for name in names:
        try:
            globals()[name]()
        except Exception as exc:                       # noqa: BLE001
            print(f"  FAIL  {name}: {type(exc).__name__}: {exc}")
            failed += 1
            continue
        control = "nc_" + name[len("test_"):]
        if control not in globals():
            print(f"  FAIL  {name}: no negative control named {control}")
            failed += 1
            continue
        try:
            globals()[control]()
        except AssertionError:
            print(f"  ok    {name}  (+ negative control)")
            passed += 1
            continue
        except Exception as exc:                       # noqa: BLE001
            print(f"  FAIL  {name}: negative control {control} raised "
                  f"{type(exc).__name__} rather than failing an assertion: {exc}")
            failed += 1
            continue
        print(f"  FAIL  {name}: negative control {control} PASSED, so the test cannot fail")
        failed += 1
    print(f"{passed} tests passed, each with a negative control that failed as it must; "
          f"{failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
