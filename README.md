# type-specimen

Point it at a font file and it produces a full specimen sheet: waterfall, metrics diagram,
running text, character set, Unicode coverage map, the font's own strongest kerning pairs, and a
demo of every OpenType feature the font declares.

**[Eight specimens, from eight real fonts](https://jesserweigel.github.io/type-specimen/)**

```bash
python3 -m typespec.cli specimen /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf -o out.html
python3 -m typespec.cli build          # the eight configured fonts, into docs/ and out/
bash scripts/verify.sh
```

Python 3 with `fonttools`. Node and a Chromium build are needed for the browser check only.

## A specimen is a claim, so every number is labelled by where it came from

The interesting failure mode for a tool like this is not a crash. It is a page that prints
`x-height: 1120` in a confident typeface for a font that contains no x-height field at all.

OS/2 gained `sxHeight` and `sCapHeight` at table version 2. A font with an older table does not
have those fields. Two of the eight fonts here are in exactly that position:

| slug | family | outlines | upem | OS/2 | x-height measured | x-height declared | cap measured | cap declared | codepoints | glyphs | kern pairs | GSUB |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `dejavu-sans` | DejaVu Sans | glyf | 2048 | 1 | 1120 | absent | 1493 | absent | 5918 | 6253 | 2727 | 13 |
| `dejavu-serif` | DejaVu Serif | glyf | 2048 | 1 | 1063 | absent | 1493 | absent | 3447 | 3528 | 1367 | 8 |
| `liberation-serif` | Liberation Serif | glyf | 2048 | 3 | 940 | 940 | 1341 | 1341 | 2321 | 2602 | 867 | 4 |
| `lato` | Lato | glyf | 2000 | 3 | 1013 | 1013 | 1433 | 1433 | 2164 | 3023 | 405928 | 20 |
| `ubuntu-variable` | Ubuntu | glyf | 1000 | 4 | 518 | 518 | 693 | 693 | 1193 | 1843 | 161054 | 20 |
| `noto-sans-mono` | Noto Sans Mono | glyf | 1000 | 4 | 536 | 536 | 714 | 714 | 3367 | 3787 | 0 | 15 |
| `tex-gyre-termes` | TeX Gyre Termes | CFF | 1000 | 3 | 450 | 450 | 662 | 662 | 1053 | 1090 | 11571 | 17 |
| `latin-modern-roman-10` | Latin Modern Roman | CFF | 1000 | 3 | 431 | 431 | 683 | 683 | 794 | 821 | 9230 | 10 |

So the specimen carries two columns rather than one. **Declared** is read from OS/2, and where the
table is too old the cell says so instead of holding a number. **Measured** is the top of the
outline of `x`, taken from the glyph itself. The exemplar glyph for each measure is named on the
page, because "x-height" without saying which letter was measured is not a measurement.

The other half of that result is worth stating too: for the six fonts that do declare these
fields, **declared and measured agree to the unit, in every case**. The two numbers are separated
because they can differ, and here they do not.

Kern pair counts are counts of distinct glyph pairs that receive a non-zero adjustment, after
expanding GPOS class-pair matrices. That is why Lato shows 405,928 from a file of a few hundred
kilobytes. Noto Sans Mono declares no kerning at all, and its specimen says so rather than
showing an empty section.

## The optical size claim, measured

Latin Modern Roman is cut at eight design sizes, and each face records the size it was cut for in
the GPOS `size` feature. The usual claim about optical sizes is that small ones are wider and sit
higher on the body. Half of that is true here:

| design size | range | x-height | cap height | x/cap | advance of `n` | word width / x-height |
|---|---|---|---|---|---|---|
| 5 | 3 to 5.5 | 431 | 683 | 0.631 | 750 | 23.03 |
| 6 | 5.5 to 6.5 | 431 | 683 | 0.631 | 676 | 20.67 |
| 7 | 6.5 to 7.5 | 431 | 683 | 0.631 | 631 | 19.25 |
| 8 | 7.5 to 8.5 | 431 | 683 | 0.631 | 590 | 17.94 |
| 9 | 8.5 to 9.5 | 431 | 683 | 0.631 | 571 | 17.37 |
| 10 | 9.5 to 11 | 431 | 683 | 0.631 | 556 | 16.90 |
| 12 | 11 to 14 | 431 | 683 | 0.631 | 544 | 16.55 |
| 17.2 | 14 to 24 | 430 | 683 | 0.630 | 511 | 15.53 |

The width claim holds and is large: the 5 pt face sets the same word 48% wider relative to its
own x-height than the 17.2 pt face, and `n` is 750 units against 511. The vertical claim does not
hold at all. x-height is 431 units per 1000 at every size from 5 to 12, and 430 at 17.2, so the
ratio to cap height moves by one part in a thousand across the whole family. Latin Modern's
optical sizes change width and stroke weight and leave the vertical proportions alone.

## A bug this found, and now tests against

The `size` feature stores its design size as decipoints in a `uint16`. fontTools' `DeciPoints`
converter has already divided by ten by the time the value reaches calling code. Dividing again
turned a 10 pt face into a 1 pt one, and the first version of this generator did exactly that.
Every optical size on the page was wrong by an order of magnitude and still looked like a
plausible table.

It is now a test with a negative control, and the independent checker compares against the raw
`uint16` from the file rather than against any interpretation of it.

## A variable font's instances are measured, not assumed

The Ubuntu file carries `wght` and `wdth` axes. Each instance is measured from the interpolated
outline at that location:

| instance | location | x-height | cap height | width of `H` |
|---|---|---|---|---|
| thin | wght 100 | 513 | 693 | 492 |
| regular | wght 400 | 518 | 693 | 519 |
| bold | wght 800 | 526 | 693 | 574 |
| condensed | wdth 75, wght 400 | 522 | 693 | 397 |

Cap height is flat across the weight axis and x-height rises by 13 units from thin to bold, which
is the optical compensation you would expect and is worth having as a number rather than as a
belief.

## OpenType feature demos say when they could not run

This is not a shaping engine. It applies GSUB lookup types 1 (single substitution) and 4
(ligature substitution). Across the eight fonts, 107 GSUB features are declared, 52 produce a
visible substitution on the sample text and 55 do not. Every one of the 55 carries its reason on
the page:

- `lookup types not implemented: 3` (alternate substitution), `: 2` (multiple), `: 6` (chaining
  context). The tag names the type so the limit is attributable.
- `positional, needs a shaper this generator does not have`, for `init`, `medi`, `fina` and
  friends.
- `no-change`, meaning the lookups ran and the sample text contains nothing they act on.

A demo that silently rendered the unfeatured string would be indistinguishable from a font whose
feature does nothing, and the reader could not tell which they were looking at.

## No font binary is redistributed

The specimen draws glyph outlines as SVG paths pulled from the font, so the published pages carry
drawn shapes rather than a font file. Nothing here needs a redistribution grant, and the pages
render identically for every reader regardless of what they have installed.

All eight fonts are on the machine as distribution packages, and each one's license permits
embedding outlines in a document in any case:

| package | license | license text on disk |
|---|---|---|
| `fonts-dejavu-core` | Bitstream Vera Fonts License, plus public domain additions (Arev) | `/usr/share/doc/fonts-dejavu-core/copyright` |
| `fonts-liberation` | SIL Open Font License 1.1 | `/usr/share/doc/fonts-liberation/copyright` |
| `fonts-lato` | SIL Open Font License 1.1 | `/usr/share/doc/fonts-lato/copyright` |
| `fonts-ubuntu` | Ubuntu Font Licence 1.0 | `/usr/share/doc/fonts-ubuntu/copyright` |
| `fonts-noto-mono` | SIL Open Font License 1.1 | `/usr/share/doc/fonts-noto-mono/copyright` |
| `tex-gyre` | GUST Font License (LPPL-derived) | `/usr/share/doc/tex-gyre/copyright` |
| `fonts-lmodern` | GUST Font License (LPPL-derived) | `/usr/share/doc/fonts-lmodern/copyright` |

`verify.sh` fails if any font binary is ever committed, and fails if any configured font or
license file is missing rather than quietly building a smaller set.

## How this is checked

**The checker shares no code with the generator.** `typespec/` reads fonts through fontTools.
`checkers/check_font_facts.py` imports only `struct`, `json`, `os`, `sys` and `hashlib`, and reads
the sfnt container itself: head, hhea, OS/2, cmap formats 0, 4, 6 and 12, hmtx, maxp, fvar, the
GSUB and GPOS feature lists, glyph bounding boxes from `glyf` with composites resolved, and glyph
bounding boxes from CFF by interpreting Type 2 charstrings and solving each cubic for its turning
points. It re-derives 304 facts across the eight fonts and the two cross-font studies, and fails
on any disagreement. A bug would have to occur identically in fontTools and in a hand-written
parser to survive.

`checkers/check_independence.py` proves that rather than asserting it, by walking the import graph
with `ast`. It checks both halves: the checker never reaches `typespec` or `fontTools` at any
depth and has no dynamic-import escape hatch, and the generator does reach `fontTools`. Without
the second half the claim would be vacuous.

**What the checker cannot do, it says.** It does not interpolate `gvar` deltas, so the three
Ubuntu instances away from the default location print `NOT CHECKED` with the reason. The
default-location instance is checked against the raw `glyf` outline.

**Every test has a negative control.** 26 tests, each paired with a deliberately wrong version of
the same situation that the test must reject. A test whose negative control passes is reported as
a failure, because it has not been shown capable of failing.

**Seven sabotages**, each proved to have applied, proved to have changed a SHA-256 fingerprint of
every generated file, and only then checked to be caught:

| sabotage | what it does |
|---|---|
| `x-height-measured-from-X` | measures the wrong letter, giving a plausible wrong number |
| `absent-os2-field-filled-in` | invents a value for an OS/2 field the font does not contain |
| `design-size-divided-twice` | reintroduces the real bug described above |
| `coverage-claims-solid-ranges` | claims every codepoint between the first and the last |
| `kerning-silently-dropped` | draws text unkerned while the page says kerning was applied |
| `unimplemented-lookup-hidden` | reports a limit of this tool as a fact about the font |
| `feature-demo-shows-after-twice` | renders the substituted run as both before and after |

**Determinism is measured, not assumed.** Two full builds are compared byte for byte, and the
committed `docs/` and `out/` are compared against a fresh build. Glyph coordinates are emitted as
integers in font units, with `-0` normalised to `0`, because the two are different bytes. No font
is subset or re-encoded at build time, so no question of WOFF2 reproducibility arises.

**A real browser loads the pages** and measures what the script must have produced: the waterfall
rows rising across nine sizes, hundreds of glyph paths with non-empty bounding boxes, and the
metrics diagram's rules in the right vertical order carrying the same numbers the independent
checker confirmed. Overflow is probed at 1280px and at 390px by walking every element and
comparing `getBoundingClientRect().right` against `clientWidth`, excusing only children of a
container with `overflow-x: auto`. `overflow-x: hidden` is excused by nothing, and `verify.sh`
fails if it appears anywhere, because it hides the bug and makes the probe vacuous. This found two
real overflows, in the running-text block and the provenance table.

**Checks that cannot run fail rather than skip.** Missing fonts, missing fontTools, missing
playwright-core and a browser that will not launch each exit non-zero with the install command
named.

## Assumptions and limits

- The eight-font set is specific to a Debian or Ubuntu machine with those packages installed.
  `python3 -m typespec.cli specimen <path>` works on any font file anywhere, and `verify.sh`
  exercises that path against a font outside the configuration.
- Only GSUB lookup types 1 and 4 are applied. Contextual, chaining and alternate substitutions
  are reported as unimplemented rather than demonstrated.
- Kerning comes from GPOS `PairPos` formats 1 and 2 and from a legacy `kern` table format 0.
  Cursive attachment, mark positioning and device tables are not applied.
- The Unicode block table is a subset of Unicode 15.0 covering the blocks these fonts touch, with
  a catch-all so no codepoint is dropped. Block names are labels; the claim that carries weight is
  the raw codepoint set, which the independent checker re-derives.
- The browser check resolves `playwright-core` from this repository, then from sibling
  directories, then from `TYPESPEC_PLAYWRIGHT_CORE`. In a clone with no sibling checkout, set that
  variable or run `npm install --no-save playwright-core`.
- Variable font instances other than the default are not independently re-derived.

## Status

VERIFY-OUTPUT-GOES-HERE

## What is not done

- No PDF output. The specimen is HTML and SVG only.
- No GPOS mark attachment, so a specimen of an Arabic or Devanagari face would draw marks in the
  wrong place. The Unicode coverage map still reports those blocks correctly, and the feature
  demos for positional features say they were not run.
- Optical size comparison covers one family, because Latin Modern is the only family on this
  machine cut at multiple sizes with a `size` feature.
- The layout is one column at a fixed measure. It does not adapt the specimen's structure to the
  kind of face it is looking at, which a specimen laid out by a person would.

## License

MIT. See `LICENSE`.

Task ART-027 from [722 things to build](https://github.com/JesseRWeigel/722-things-to-build).
