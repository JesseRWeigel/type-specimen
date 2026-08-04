"""Unicode block ranges, and the sample text a specimen sets.

The block table is a labelling aid. The claim that carries weight is the raw codepoint set read
from the cmap, which the independent checker re-derives from the font's bytes; blocks only decide
which heading a covered codepoint is counted under. It is a subset of Unicode 15.0 Blocks.txt,
covering the blocks these fonts actually touch, plus a catch-all so nothing is silently dropped.
"""

from __future__ import annotations

# (start, end, name). Inclusive, disjoint, ascending. tests/ asserts all three.
BLOCKS = [
    (0x0000, 0x007F, "Basic Latin"),
    (0x0080, 0x00FF, "Latin-1 Supplement"),
    (0x0100, 0x017F, "Latin Extended-A"),
    (0x0180, 0x024F, "Latin Extended-B"),
    (0x0250, 0x02AF, "IPA Extensions"),
    (0x02B0, 0x02FF, "Spacing Modifier Letters"),
    (0x0300, 0x036F, "Combining Diacritical Marks"),
    (0x0370, 0x03FF, "Greek and Coptic"),
    (0x0400, 0x04FF, "Cyrillic"),
    (0x0500, 0x052F, "Cyrillic Supplement"),
    (0x0530, 0x058F, "Armenian"),
    (0x0590, 0x05FF, "Hebrew"),
    (0x0600, 0x06FF, "Arabic"),
    (0x0700, 0x074F, "Syriac"),
    (0x0780, 0x07BF, "Thaana"),
    (0x0900, 0x097F, "Devanagari"),
    (0x0E00, 0x0E7F, "Thai"),
    (0x10A0, 0x10FF, "Georgian"),
    (0x1D00, 0x1D7F, "Phonetic Extensions"),
    (0x1E00, 0x1EFF, "Latin Extended Additional"),
    (0x1F00, 0x1FFF, "Greek Extended"),
    (0x2000, 0x206F, "General Punctuation"),
    (0x2070, 0x209F, "Superscripts and Subscripts"),
    (0x20A0, 0x20CF, "Currency Symbols"),
    (0x20D0, 0x20FF, "Combining Marks for Symbols"),
    (0x2100, 0x214F, "Letterlike Symbols"),
    (0x2150, 0x218F, "Number Forms"),
    (0x2190, 0x21FF, "Arrows"),
    (0x2200, 0x22FF, "Mathematical Operators"),
    (0x2300, 0x23FF, "Miscellaneous Technical"),
    (0x2400, 0x243F, "Control Pictures"),
    (0x2440, 0x245F, "Optical Character Recognition"),
    (0x2460, 0x24FF, "Enclosed Alphanumerics"),
    (0x2500, 0x257F, "Box Drawing"),
    (0x2580, 0x259F, "Block Elements"),
    (0x25A0, 0x25FF, "Geometric Shapes"),
    (0x2600, 0x26FF, "Miscellaneous Symbols"),
    (0x2700, 0x27BF, "Dingbats"),
    (0x27C0, 0x27EF, "Miscellaneous Mathematical Symbols-A"),
    (0x27F0, 0x27FF, "Supplemental Arrows-A"),
    (0x2800, 0x28FF, "Braille Patterns"),
    (0x2900, 0x297F, "Supplemental Arrows-B"),
    (0x2980, 0x29FF, "Miscellaneous Mathematical Symbols-B"),
    (0x2A00, 0x2AFF, "Supplemental Mathematical Operators"),
    (0x2B00, 0x2BFF, "Miscellaneous Symbols and Arrows"),
    (0x2C60, 0x2C7F, "Latin Extended-C"),
    (0x2E00, 0x2E7F, "Supplemental Punctuation"),
    (0x3000, 0x303F, "CJK Symbols and Punctuation"),
    (0x4E00, 0x9FFF, "CJK Unified Ideographs"),
    (0xA720, 0xA7FF, "Latin Extended-D"),
    (0xAB30, 0xAB6F, "Latin Extended-E"),
    (0xFB00, 0xFB4F, "Alphabetic Presentation Forms"),
    (0xFE20, 0xFE2F, "Combining Half Marks"),
    (0xFEFF, 0xFEFF, "Specials (BOM)"),
    (0xFFF0, 0xFFFF, "Specials"),
    (0x1D400, 0x1D7FF, "Mathematical Alphanumeric Symbols"),
    (0x1F300, 0x1F5FF, "Miscellaneous Symbols and Pictographs"),
    (0x1F600, 0x1F64F, "Emoticons"),
]

UNASSIGNED_LABEL = "Other blocks"


def bucket(codepoints):
    """Covered counts per named block. Ascending by block start; the catch-all sorts last."""
    counts = {}
    other = 0
    starts = [b[0] for b in BLOCKS]
    import bisect
    for cp in codepoints:
        i = bisect.bisect_right(starts, cp) - 1
        if i >= 0 and BLOCKS[i][0] <= cp <= BLOCKS[i][1]:
            counts[BLOCKS[i][2]] = counts.get(BLOCKS[i][2], 0) + 1
        else:
            other += 1
    out = []
    for start, end, name in BLOCKS:
        if name in counts:
            out.append({"name": name, "start": start, "end": end,
                        "covered": counts[name], "size": end - start + 1})
    if other:
        out.append({"name": UNASSIGNED_LABEL, "start": None, "end": None,
                    "covered": other, "size": None})
    return out


# ---------------------------------------------------------------------------
# Sample text. Chosen once, here, so no rendering code invents a string inline.

WATERFALL_LINE = "Hamburgefonstiv 0123456789"
WATERFALL_SIZES = [9, 11, 13, 16, 20, 26, 34, 46, 64]
METRIC_WORD = "Hxbpd8"
PARAGRAPH = (
    "The specimen sheet is the only honest advertisement a typeface has. It sets the face at the "
    "sizes it claims to work at, shows the characters it actually contains, and lets the reader "
    "decide. Every number on this page was read out of the font file."
)
CHARSET = (
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "abcdefghijklmnopqrstuvwxyz"
    "0123456789"
    "&@#$%*+-=/\\<>()[]{}|~^"
    ".,:;!?'\"`‘’“”–—…·"
    "ÀÇÉÑÖÜßàçéîñöü"
    "ŁŒŠŽłœšž"
    "¡¿©®°±×÷§¶†‡"
    "€£¥¢¤№™"
    "ΑΒΓΔΩαβγδω"
    "АБВГДЖабвгдж"
)

FEATURE_SAMPLES = {
    "liga": "office affluent fjord flight",
    "dlig": "ct st sp Th",
    "hlig": "ct st sp",
    "rlig": "fi fl ffi",
    "clig": "office fjord",
    "calt": "AVATAR Two Yo",
    "smcp": "Small Caps Here",
    "c2sc": "SMALL CAPS HERE",
    "onum": "0123456789 in 1847",
    "lnum": "0123456789 in 1847",
    "tnum": "1111 0000 8888",
    "pnum": "1111 0000 8888",
    "frac": "1/2 3/4 5/8",
    "zero": "0 100 0.05",
    "sups": "123abc",
    "subs": "123abc",
    "sinf": "H2O 123",
    "numr": "123",
    "dnom": "456",
    "ordn": "1a 2o No",
    "case": "¿HOLA! (A) -A- «A»",
    "salt": "agRQKy",
    "aalt": "agRQKy",
    "ss01": "agRQKy 0123",
    "ss02": "agRQKy 0123",
    "ss03": "agRQKy 0123",
    "ss04": "agRQKy 0123",
    "ss10": "agRQKy 0123",
    "locl": "áàäã łż",
    "ccmp": "áé́ fi",
    "subs2": "123",
    "ordinals": "1a 2o",
}
FEATURE_SAMPLE_DEFAULT = "Hamburgefonstiv 0123"

# Features whose behaviour is positional or contextual in a script this generator does not shape.
POSITIONAL_FEATURES = {"init", "medi", "fina", "isol", "rtlm", "mset", "ssty", " RQD"}

FEATURE_NAMES = {
    "aalt": "Access All Alternates", "c2sc": "Capitals to Small Capitals",
    "calt": "Contextual Alternates", "case": "Case-Sensitive Forms",
    "ccmp": "Glyph Composition and Decomposition", "clig": "Contextual Ligatures",
    "cpsp": "Capital Spacing", "dlig": "Discretionary Ligatures", "dnom": "Denominators",
    "fina": "Terminal Forms", "frac": "Fractions", "hlig": "Historical Ligatures",
    "init": "Initial Forms", "kern": "Kerning", "liga": "Standard Ligatures",
    "lnum": "Lining Figures", "locl": "Localized Forms", "mark": "Mark Positioning",
    "medi": "Medial Forms", "mkmk": "Mark to Mark Positioning", "numr": "Numerators",
    "onum": "Oldstyle Figures", "ordn": "Ordinals", "pnum": "Proportional Figures",
    "rlig": "Required Ligatures", "rtlm": "Right-to-Left Mirrored Forms",
    "salt": "Stylistic Alternates", "sinf": "Scientific Inferiors", "size": "Optical Size",
    "smcp": "Small Capitals", "ssty": "Math Script Style", "subs": "Subscript",
    "sups": "Superscript", "tnum": "Tabular Figures", "zero": "Slashed Zero",
}


def feature_name(tag):
    if tag in FEATURE_NAMES:
        return FEATURE_NAMES[tag]
    if tag.startswith("ss") and tag[2:].isdigit():
        return f"Stylistic Set {int(tag[2:])}"
    if tag.startswith("cv") and tag[2:].isdigit():
        return f"Character Variant {int(tag[2:])}"
    return "unnamed in the OpenType feature registry"


def feature_sample(tag):
    return FEATURE_SAMPLES.get(tag, FEATURE_SAMPLE_DEFAULT)
