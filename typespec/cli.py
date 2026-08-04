"""Build specimens.

    python3 -m typespec.cli build                 # the configured set, into docs/ and out/
    python3 -m typespec.cli specimen FONT [-o F]  # any font file on the machine

Output is deterministic: the same font files always produce the same bytes.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from fontTools.ttLib import TTFont

from . import draw, shape, site
from .draw import esc
from .probe import probe
from .specimen import Specimen

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPTICAL_WORD = "Handgloves 1847"
OPTICAL_SIZE = 40


def load_config(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def check_fonts_present(config):
    """Every configured path, or an actionable failure. A missing font is not a reason to skip."""
    missing = []
    for entry in config["fonts"]:
        if not os.path.exists(entry["path"]):
            missing.append((entry["path"], entry["package"]))
    for path in config["optical_family"]["members"]:
        if not os.path.exists(path):
            missing.append((path, config["optical_family"]["package"]))
    return missing


def build(config_path, docs_dir, facts_dir):
    config = load_config(config_path)
    missing = check_fonts_present(config)
    if missing:
        packages = sorted({pkg for _, pkg in missing})
        print("These configured fonts are not on this machine:", file=sys.stderr)
        for path, pkg in missing:
            print(f"  {path}   (package {pkg})", file=sys.stderr)
        print("\nInstall them with:\n  sudo apt-get install " + " ".join(packages),
              file=sys.stderr)
        print("Nothing was built. A specimen of a font that is not here would be fiction.",
              file=sys.stderr)
        return 2

    os.makedirs(docs_dir, exist_ok=True)
    os.makedirs(facts_dir, exist_ok=True)

    all_facts, cards = [], []
    for entry in config["fonts"]:
        facts = probe(entry["path"])
        facts["slug"] = entry["slug"]
        facts["license"] = entry["license"]
        facts["license_file"] = entry["license_file"]
        facts["package"] = entry["package"]
        spec = Specimen(entry["path"], facts)
        facts["kern_pair_count"] = len(spec.shaper.kern)
        write(os.path.join(facts_dir, entry["slug"] + ".json"),
              json.dumps(facts, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
        write(os.path.join(docs_dir, entry["slug"] + ".html"),
              site.specimen_page(spec, entry))
        cards.append(card(spec, entry))
        spec.close()
        all_facts.append(facts)

    variable = variable_study(config, facts_dir)
    optical, optical_html = optical_study(config, facts_dir)

    write(os.path.join(facts_dir, "_index.json"),
          json.dumps({"fonts": [_summary(f) for f in all_facts],
                      "optical": optical,
                      "variable": variable},
                     indent=2, sort_keys=True, ensure_ascii=False) + "\n")

    write(os.path.join(docs_dir, "index.html"),
          site.index_page("".join(cards), comparison_table(all_facts),
                          optical_html + variable_html(variable),
                          len(all_facts), license_table(config)))
    print(f"built {len(all_facts)} specimens into {os.path.relpath(docs_dir, REPO)}/ "
          f"and facts into {os.path.relpath(facts_dir, REPO)}/")
    return 0


def _summary(facts):
    m, d = facts["measured"], facts["declared"]
    upem = d["units_per_em"]

    def permille(value):
        return None if value is None else round(1000.0 * value / upem, 1)

    return {
        "slug": facts["slug"],
        "family": facts["family"],
        "subfamily": facts["subfamily"],
        "outline_format": facts["outline_format"],
        "units_per_em": upem,
        "os2_version": d["os2_version"],
        "glyph_count": facts["glyph_count"],
        "codepoint_count": facts["coverage"]["codepoint_count"],
        "kern_pair_count": facts["kern_pair_count"],
        "gsub_feature_count": len(facts["features"]["GSUB"]),
        "gpos_feature_count": len(facts["features"]["GPOS"]),
        "x_height_declared": d["x_height"],
        "x_height_measured": m["x_height"]["value"] if m["x_height"]["available"] else None,
        "x_height_declared_permille": permille(d["x_height"]),
        "x_height_measured_permille": permille(
            m["x_height"]["value"] if m["x_height"]["available"] else None),
        "cap_height_declared": d["cap_height"],
        "cap_height_measured": m["cap_height"]["value"] if m["cap_height"]["available"] else None,
        "license": facts["license"],
    }


def card(spec, entry):
    f = spec.facts
    s = _summary(f)
    xd = "absent" if s["x_height_declared"] is None else str(s["x_height_declared"])
    return (f'<div class="card"><h3><a href="{esc(entry["slug"])}.html">'
            f'{esc(spec.label)}</a></h3>'
            f'<p class="sub">{esc(entry["license"])}</p>'
            f'<dl>'
            f'<dt>outlines</dt><dd>{esc(f["outline_format"])}</dd>'
            f'<dt>glyphs</dt><dd>{f["glyph_count"]}</dd>'
            f'<dt>codepoints</dt><dd>{f["coverage"]["codepoint_count"]}</dd>'
            f'<dt>units per em</dt><dd>{s["units_per_em"]}</dd>'
            f'<dt>OS/2 version</dt><dd>{s["os2_version"]}</dd>'
            f'<dt>x-height declared</dt><dd>{esc(xd)}</dd>'
            f'<dt>x-height measured</dt><dd>{s["x_height_measured"]}</dd>'
            f'<dt>kern pairs</dt><dd>{f["kern_pair_count"]}</dd>'
            f'<dt>GSUB features</dt><dd>{len(f["features"]["GSUB"])}</dd>'
            f'</dl>'
            f'<p class="note">{esc(entry["why"])}</p></div>')


def comparison_table(all_facts):
    rows = []
    for facts in all_facts:
        s = _summary(facts)
        def cell(declared, measured):
            if declared is None:
                return ('<td class="num"><i>absent</i></td>'
                        f'<td class="num">{measured}</td><td class="num">&mdash;</td>')
            delta = measured - declared
            return (f'<td class="num">{declared}</td><td class="num">{measured}</td>'
                    f'<td class="num">{delta:+d}</td>')
        rows.append(
            f'<tr><td><a href="{esc(s["slug"])}.html">{esc(s["family"])}</a></td>'
            f'<td class="num">{s["units_per_em"]}</td>'
            f'<td class="num">{s["os2_version"]}</td>'
            + cell(s["x_height_declared"], s["x_height_measured"])
            + cell(s["cap_height_declared"], s["cap_height_measured"])
            + f'<td class="num">{s["codepoint_count"]}</td>'
            f'<td class="num">{s["kern_pair_count"]}</td></tr>')
    return ('<div class="scroll"><table><thead><tr><th>font</th><th class="num">upem</th>'
            '<th class="num">OS/2</th><th class="num">x-ht decl</th><th class="num">x-ht meas</th>'
            '<th class="num">&Delta;</th><th class="num">cap decl</th><th class="num">cap meas</th>'
            '<th class="num">&Delta;</th><th class="num">codepoints</th>'
            '<th class="num">kern pairs</th></tr></thead><tbody>'
            + "".join(rows) + "</tbody></table></div>")


def license_table(config):
    rows = []
    seen = set()
    for entry in config["fonts"] + [config["optical_family"]]:
        key = (entry.get("package"), entry["license"])
        if key in seen:
            continue
        seen.add(key)
        rows.append(f'<tr><td>{esc(entry.get("package", entry.get("name", "")))}</td>'
                    f'<td>{esc(entry["license"])}</td>'
                    f'<td class="mono">{esc(entry["license_file"])}</td></tr>')
    return ('<div class="scroll"><table><thead><tr><th>package</th><th>license</th>'
            '<th>license text</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table></div>")


# ---------------------------------------------------------------------------
# Optical sizes

def optical_study(config, facts_dir):
    """Latin Modern Roman at its eight design sizes.

    The design size is read from the GPOS `size` feature, which is where a font actually records
    what size it was cut for. The claim that small optical sizes are proportionally wider and
    larger on the body is then measured rather than repeated.
    """
    family = config["optical_family"]
    members, rows, svg_rows = [], [], []
    y = 12
    max_w = 0
    for path in family["members"]:
        facts = probe(path)
        font = TTFont(path, fontNumber=0, lazy=True)
        shaper = shape.Shaper(font)
        painter = draw.Painter(shaper.glyph_set, shaper.upem)
        upem = shaper.upem
        n_glyph = shaper.cmap.get(ord("n"))
        glyphs, _ = shaper.to_glyphs(OPTICAL_WORD)
        placed, width = shaper.position(glyphs)
        size_feature = facts["size_feature"]
        x_h = facts["measured"]["x_height"]["value"]
        cap = facts["measured"]["cap_height"]["value"]
        entry = {
            "file_name": facts["file_name"],
            "file_sha256": facts["file_sha256"],
            "file_bytes": facts["file_bytes"],
            "design_size": None if size_feature is None else size_feature["design_size"],
            "design_size_decipoints": (None if size_feature is None
                                       else size_feature["raw_decipoints"]["design_size"]),
            "range_start": None if size_feature is None else size_feature["range_start"],
            "range_end": None if size_feature is None else size_feature["range_end"],
            "units_per_em": upem,
            "x_height": x_h,
            "cap_height": cap,
            "x_over_cap": round(x_h / cap, 4),
            "advance_n": shaper.advance(n_glyph),
            "advance_n_over_x_height": round(shaper.advance(n_glyph) / x_h, 4),
            "word_width": width,
            "word_width_over_x_height": round(width / x_h, 4),
        }
        members.append(entry)
        width_px = width * OPTICAL_SIZE / upem
        max_w = max(max_w, width_px)
        baseline = y + OPTICAL_SIZE * 0.8
        label = "no size feature" if entry["design_size"] is None else f'{entry["design_size"]:g} pt'
        svg_rows.append(f'<text class="tick" x="52" y="{baseline:.2f}" text-anchor="end">'
                        f'{esc(label)}</text>')
        svg_rows.append(draw.text_group(painter, placed, OPTICAL_SIZE, 62, baseline))
        y += OPTICAL_SIZE * 1.5
        font.close()

    for m in members:
        design = "&mdash;" if m["design_size"] is None else format(m["design_size"], "g")
        span = ("&mdash;" if m["range_start"] is None
                else format(m["range_start"], "g") + "&ndash;" + format(m["range_end"], "g"))
        rows.append(
            f'<tr><td class="mono">{esc(m["file_name"])}</td>'
            f'<td class="num">{design}</td>'
            f'<td class="num">{span}</td>'
            f'<td class="num">{m["x_height"]}</td><td class="num">{m["cap_height"]}</td>'
            f'<td class="num">{m["x_over_cap"]:.3f}</td>'
            f'<td class="num">{m["advance_n"]}</td>'
            f'<td class="num">{m["word_width_over_x_height"]:.3f}</td></tr>')

    finding = _optical_finding(members)
    html = (
        f'<p class="lede">{esc(family["name"])} is cut at eight design sizes, and each face '
        f'records the size it was cut for in the GPOS <code>size</code> feature. All eight are '
        f'set below at the same em size, so what changes is the design and not the scaling.</p>'
        + f'<div class="scroll">{draw.svg(max(880, max_w + 80), y, "".join(svg_rows), "optical")}</div>'
        + '<div class="scroll"><table><thead><tr><th>file</th><th class="num">design size</th>'
          '<th class="num">range</th><th class="num">x-height</th><th class="num">cap height</th>'
          '<th class="num">x/cap</th><th class="num">adv ‘n’</th>'
          '<th class="num">word width / x-height</th></tr></thead><tbody>'
        + "".join(rows) + "</tbody></table></div>"
        + f'<p class="note">{finding}</p>')
    return {"family": family["name"], "license": family["license"], "members": members}, html


def _optical_finding(members):
    sized = [m for m in members if m["design_size"] is not None]
    if len(sized) < 2:
        return ("Fewer than two faces in this family declare a size feature, so no trend can be "
                "stated.")
    sized.sort(key=lambda m: m["design_size"])
    small, large = sized[0], sized[-1]
    parts = [
        f"From {small['design_size']:g} pt to {large['design_size']:g} pt the x-height moves from "
        f"{small['x_height']} to {large['x_height']} units per {small['units_per_em']}, "
        f"x-height over cap height from {small['x_over_cap']:.3f} to {large['x_over_cap']:.3f}, "
        f"and the width of the sample word relative to its own x-height from "
        f"{small['word_width_over_x_height']:.2f} to {large['word_width_over_x_height']:.2f}."
    ]
    if small["word_width_over_x_height"] > large["word_width_over_x_height"]:
        parts.append("The small size is proportionally wider, which is the expected direction.")
    else:
        parts.append("The small size is proportionally narrower here, against the usual claim.")
    if small["x_over_cap"] > large["x_over_cap"]:
        parts.append("It also sits higher on the body.")
    else:
        parts.append("Its x-height relative to cap height is not larger, against the usual claim.")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Variable font instances

def variable_study(config, facts_dir):
    out = []
    for slug, instances in sorted(config.get("variable_instances", {}).items()):
        entry = next((e for e in config["fonts"] if e["slug"] == slug), None)
        if entry is None:
            continue
        for inst in instances:
            facts = probe(entry["path"], location=inst["location"])
            axes = facts["fvar"] or []
            defaults = {a["tag"]: a["default"] for a in axes}
            at_default = all(defaults.get(k) == v for k, v in inst["location"].items())
            out.append({
                "slug": slug,
                "suffix": inst["suffix"],
                "file_name": facts["file_name"],
                "file_sha256": facts["file_sha256"],
                "file_bytes": facts["file_bytes"],
                "location": dict(sorted(inst["location"].items())),
                "is_default_instance": at_default,
                "x_height": facts["measured"]["x_height"]["value"],
                "cap_height": facts["measured"]["cap_height"]["value"],
                "H_bbox": facts["measured"]["cap_height"]["bbox"],
                "units_per_em": facts["declared"]["units_per_em"],
                "axes": axes,
            })
    return out


def variable_html(variable):
    if not variable:
        return ""
    rows = []
    for v in variable:
        bbox = v["H_bbox"]
        loc = ", ".join(f"{k} {g:g}" for k, g in sorted(v["location"].items()))
        rows.append(f'<tr><td>{esc(v["suffix"])}</td><td class="mono">{esc(loc)}</td>'
                    f'<td class="num">{v["x_height"]}</td><td class="num">{v["cap_height"]}</td>'
                    f'<td class="num">{bbox[2] - bbox[0]}</td></tr>')
    return ('<h3>A variable font’s instances are measured, not assumed</h3>'
            '<p class="lede">The same file, drawn at four points in its design space. The width '
            'of ‘H’ comes from the interpolated outline at each location, so it is a measurement '
            'of that instance rather than of the default.</p>'
            '<div class="scroll"><table><thead><tr><th>instance</th><th>location</th>'
            '<th class="num">x-height</th><th class="num">cap height</th>'
            '<th class="num">‘H’ width</th></tr></thead><tbody>'
            + "".join(rows) + "</tbody></table></div>")


def write(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def one_specimen(font_path, out_path):
    if not os.path.exists(font_path):
        print(f"no such font file: {font_path}", file=sys.stderr)
        return 2
    facts = probe(font_path)
    facts["slug"] = os.path.splitext(os.path.basename(font_path))[0]
    facts["license"] = "not checked, this font was passed on the command line"
    spec = Specimen(font_path, facts)
    facts["kern_pair_count"] = len(spec.shaper.kern)
    entry = {"slug": facts["slug"], "license": facts["license"],
             "package": "", "license_file": "",
             "why": ""}
    html = site.specimen_page(spec, entry)
    spec.close()
    write(out_path, html)
    print(f"wrote {out_path} for {facts['family']} "
          f"({facts['coverage']['codepoint_count']} codepoints, "
          f"{facts['glyph_count']} glyphs)")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="typespec")
    sub = parser.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build the configured specimen set")
    b.add_argument("--config", default=os.path.join(REPO, "fonts.json"))
    b.add_argument("--docs", default=os.path.join(REPO, "docs"))
    b.add_argument("--facts", default=os.path.join(REPO, "out"))
    s = sub.add_parser("specimen", help="build one specimen from any font file")
    s.add_argument("font")
    s.add_argument("-o", "--out", default="specimen.html")
    args = parser.parse_args(argv)
    if args.cmd == "build":
        return build(args.config, args.docs, args.facts)
    return one_specimen(args.font, args.out)


if __name__ == "__main__":
    sys.exit(main())
