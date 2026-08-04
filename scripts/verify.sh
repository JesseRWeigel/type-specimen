#!/usr/bin/env bash
# Verification for type-specimen.
#
# A specimen sheet is a claim about a font, made in a form that looks authoritative. The failure
# mode is not a crash, it is a page that prints a confident x-height for a font that does not
# contain one. So the checks here are arranged around what could be quietly wrong:
#
#   1  the fonts are actually on this machine, or nothing below means anything
#   2  the unit suite, every test with a negative control that must fail
#   3  the committed pages match a fresh build
#   4  two builds compared byte for byte, so "deterministic" is measured
#   5  every number re-derived from the font's bytes by a checker that shares no code
#   6  that no-shared-code claim proved with an ast import graph, not asserted
#   7  a real browser, with the outlines measured on screen
#   8  the generator pointed at a font outside its own configuration
#   9  sabotages, each proved to have applied, to have changed the output, and to be caught
#  10  hygiene, including the README's own numbers
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
ROOT="$PWD"
pass=0; fail=0
ok()  { printf '  ok    %s\n' "$1"; pass=$((pass+1)); }
bad() { printf '  FAIL  %s\n' "$1"; fail=$((fail+1)); }
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

echo "0. environment"
python3 --version | sed 's/^/        /'
node --version | sed 's/^/        node /'
if python3 -c "import fontTools; print('        fontTools', fontTools.version)" 2>/dev/null; then
  ok "python3, node and fontTools present"
else
  bad "fontTools is not installed. Install it with: pip3 install fonttools"
  echo "        Nothing below can run without it, so this is a failure and not a skip."
  echo; printf '%d passed, %d failed\n' "$pass" "$fail"; echo "VERIFY FAILED"; exit 1
fi

echo
echo "1. the fonts this repository describes are on this machine"
if python3 - <<'PY' >"$TMP/fonts.log" 2>&1; then
import json, os, sys
config = json.load(open("fonts.json"))
missing = []
for entry in config["fonts"]:
    if not os.path.exists(entry["path"]):
        missing.append((entry["path"], entry["package"]))
for path in config["optical_family"]["members"]:
    if not os.path.exists(path):
        missing.append((path, config["optical_family"]["package"]))
for entry in config["fonts"] + [config["optical_family"]]:
    if not os.path.exists(entry["license_file"]):
        missing.append((entry["license_file"], entry["package"]))
if missing:
    packages = sorted({p for _, p in missing})
    print(f"{len(missing)} configured path(s) are not here, starting with {missing[0][0]}")
    print("  sudo apt-get install " + " ".join(packages))
    print("This is a FAILURE, not a skip. A specimen of a font that is not here would be fiction.")
    sys.exit(1)
print(f"{len(config['fonts'])} fonts and {len(config['optical_family']['members'])} optical "
      f"sizes present, with their license text on disk")
PY
  sed 's/^/        /' "$TMP/fonts.log"; ok "every configured font and license file is present"
else
  sed 's/^/        /' "$TMP/fonts.log"; bad "configured fonts are missing"
  echo; printf '%d passed, %d failed\n' "$pass" "$fail"; echo "VERIFY FAILED"; exit 1
fi

echo
echo "2. unit suite"
if python3 tests/run.py >"$TMP/t.log" 2>&1; then
  ok "$(tail -1 "$TMP/t.log")"
else
  bad "the suite failed"; grep FAIL "$TMP/t.log" | head -8 | sed 's/^/        /'
fi
TEST_COUNT="$(grep -c '^  ok ' "$TMP/t.log" || true)"

echo
echo "3. the committed pages match a fresh build"
cp -r docs "$TMP/docs.committed"; cp -r out "$TMP/out.committed"
if python3 -m typespec.cli build >"$TMP/build.log" 2>&1; then
  sed 's/^/        /' "$TMP/build.log"
  if diff -r "$TMP/docs.committed" docs >/dev/null 2>&1 && \
     diff -r "$TMP/out.committed" out >/dev/null 2>&1; then
    ok "docs/ and out/ are exactly what the generator produces now"
  else
    bad "the committed docs/ or out/ differ from a fresh build"
    diff -rq "$TMP/docs.committed" docs 2>&1 | head -4 | sed 's/^/        /'
    diff -rq "$TMP/out.committed" out 2>&1 | head -4 | sed 's/^/        /'
  fi
else
  bad "the build failed"; tail -5 "$TMP/build.log" | sed 's/^/        /'
fi

echo
echo "4. determinism, two independent builds compared byte for byte"
mkdir -p "$TMP/d1/docs" "$TMP/d1/out" "$TMP/d2/docs" "$TMP/d2/out"
if python3 -m typespec.cli build --docs "$TMP/d1/docs" --facts "$TMP/d1/out" >/dev/null 2>&1 && \
   python3 -m typespec.cli build --docs "$TMP/d2/docs" --facts "$TMP/d2/out" >/dev/null 2>&1; then
  if diff -r "$TMP/d1" "$TMP/d2" >/dev/null 2>&1; then
    bytes=$(cat "$TMP"/d1/docs/* "$TMP"/d1/out/* | wc -c)
    files=$(find "$TMP/d1" -type f | wc -l)
    ok "$files files, $bytes bytes, identical across two runs"
  else
    bad "two builds differ"; diff -rq "$TMP/d1" "$TMP/d2" | head -4 | sed 's/^/        /'
  fi
else
  bad "a repeat build failed"
fi

echo
echo "5. every fact re-derived from the font bytes, independently"
if python3 checkers/check_font_facts.py out/*.json >"$TMP/facts.log" 2>&1; then
  grep -E '^(ok|FAIL|[0-9]+ facts)' "$TMP/facts.log" | sed 's/^/        /'
  grep -E 'NOT CHECKED|COULD NOT CHECK' "$TMP/facts.log" | sed 's/^/        /' || true
  ok "$(tail -1 "$TMP/facts.log")"
else
  bad "the independent re-derivation disagrees with the generator"
  grep -A4 FAIL "$TMP/facts.log" | head -12 | sed 's/^/        /'
fi

echo
echo "6. the checker really is independent, proved by import graph"
if python3 checkers/check_independence.py >"$TMP/ind.log" 2>&1; then
  sed 's/^/        /' "$TMP/ind.log"
  ok "no shared code between generator and checker"
else
  bad "the independence proof failed"; sed 's/^/        /' "$TMP/ind.log"
fi

echo
echo "7. a real browser"
if node scripts/browser_check.mjs >"$TMP/br.log" 2>&1; then
  grep -E '^  (ok|FAIL)' "$TMP/br.log" | sed 's/^/      /'
  ok "$(tail -1 "$TMP/br.log")"
else
  rc=$?
  bad "the browser check failed (exit $rc)"
  tail -14 "$TMP/br.log" | sed 's/^/        /'
fi

echo
echo "8. the generator points at a font it was not configured for"
UNCONFIGURED="/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
if [ ! -f "$UNCONFIGURED" ]; then
  bad "the ad-hoc font $UNCONFIGURED is not installed, so this check could not run"
elif python3 -m typespec.cli specimen "$UNCONFIGURED" -o "$TMP/adhoc.html" >"$TMP/adhoc.log" 2>&1
then
  sed 's/^/        /' "$TMP/adhoc.log"
  if python3 - "$TMP/adhoc.html" "$UNCONFIGURED" <<'PY' >"$TMP/adhoc2.log" 2>&1; then
import re, sys
from fontTools.ttLib import TTFont
from fontTools.pens.boundsPen import BoundsPen
html = open(sys.argv[1], encoding="utf-8").read()
font = TTFont(sys.argv[2], lazy=True)
cmap = font.getBestCmap()
gs = font.getGlyphSet()
pen = BoundsPen(gs); gs[cmap[ord("x")]].draw(pen)
x_height = int(round(pen.bounds[3]))
if str(x_height) not in html:
    sys.exit(f"the page does not contain the measured x-height {x_height}")
if str(len(cmap)) not in html:
    sys.exit(f"the page does not contain the codepoint count {len(cmap)}")
paths = len(re.findall(r'<path ', html))
if paths < 150:
    sys.exit(f"only {paths} glyph outlines drawn")
print(f"an unconfigured font produced {paths} outlines, x-height {x_height}, "
      f"{len(cmap)} codepoints, all matching the file")
PY
    sed 's/^/        /' "$TMP/adhoc2.log"; ok "it works on any font file, not only the eight"
  else bad "$(cat "$TMP/adhoc2.log")"; fi
else
  bad "the ad-hoc specimen failed"; tail -4 "$TMP/adhoc.log" | sed 's/^/        /'
fi

echo
echo "9. sabotage"
# The fingerprint every sabotage must move. Both the facts and the rendered pages, because a
# sabotage can leave the numbers alone and still make the drawing lie.
fingerprint() { cat "$1"/out/*.json "$1"/docs/*.html 2>/dev/null | sha256sum | cut -c1-16; }
BASE_FP="$(fingerprint "$ROOT")"
echo "        baseline fingerprint $BASE_FP"

attack() {
  local name="$1" file="$2" old="$3" new="$4"
  local dir="$TMP/a-$name"; rm -rf "$dir"; mkdir -p "$dir"
  tar -cf - --exclude=.git --exclude=node_modules --exclude=__pycache__ -C "$ROOT" . \
    | tar -xf - -C "$dir"
  # 1. it applied
  if ! python3 scripts/patch.py "$dir/$file" "$old" "$new" >"$TMP/$name.patch" 2>&1; then
    bad "sabotage \"$name\" did not apply, so it proves nothing"
    sed 's/^/        /' "$TMP/$name.patch"; return
  fi
  # 2. it changed the output
  ( cd "$dir" && python3 -m typespec.cli build ) >"$TMP/$name.build" 2>&1
  local new_fp; new_fp="$(fingerprint "$dir")"
  if [ "$new_fp" = "$BASE_FP" ]; then
    bad "sabotage \"$name\" left the output byte for byte identical, so it proves nothing"
    return
  fi
  # 3. something noticed
  local trc crc
  ( cd "$dir" && python3 tests/run.py ) >"$TMP/$name.test" 2>&1; trc=$?
  ( cd "$dir" && python3 checkers/check_font_facts.py out/*.json ) >"$TMP/$name.chk" 2>&1; crc=$?
  printf '        %-28s output %s -> %s, suite exit %s, checker exit %s\n' \
    "$name" "$BASE_FP" "$new_fp" "$trc" "$crc"
  if [ "$trc" -ne 0 ] || [ "$crc" -ne 0 ]; then
    { grep -m1 '^  FAIL' "$TMP/$name.test"; grep -m1 '^        ' "$TMP/$name.chk"; } 2>/dev/null \
      | head -2 | cut -c1-118 | sed 's/^/          /'
    ok "sabotage \"$name\" is caught"
  else
    bad "sabotage \"$name\" changed the output and neither the suite nor the checker noticed"
  fi
}

# Measure the wrong letter. The number stays plausible, which is what makes it dangerous.
attack "x-height-measured-from-X" "typespec/probe.py" \
  '    "x_height": "x",' \
  '    "x_height": "X",'
# Invent a value for an OS/2 field the font does not contain. This is the failure this whole
# project is arranged around.
attack "absent-os2-field-filled-in" "typespec/probe.py" \
  '        declared[key] = None if value is None else int(value)' \
  '        declared[key] = int(value) if value is not None else int(upem * 0.52)'
# Divide the design size by ten a second time. This bug was real and shipped once here.
attack "design-size-divided-twice" "typespec/probe.py" \
  '            "design_size": float(design),' \
  '            "design_size": float(design) / 10.0,'
# Claim every codepoint between the first and the last, which is what a lazy coverage map does.
attack "coverage-claims-solid-ranges" "typespec/probe.py" \
  '    return {cp for cp, gname in best.items() if gname != ".notdef"}' \
  '    return set(range(min(best), max(best) + 1))'
# Draw the text without the kerning the specimen says it applied.
attack "kerning-silently-dropped" "typespec/shape.py" \
  '                x += self.kern.get((gname, glyph_names[i + 1]), 0)' \
  '                x += 0'
# Report an unimplementable feature as simply having no effect, which reads as a fact about the
# font rather than a limit of this tool.
attack "unimplemented-lookup-hidden" "typespec/shape.py" \
  '                skipped.add(lt)' \
  '                pass'
# Render the substituted run twice, so every feature demo looks like it worked.
attack "feature-demo-shows-after-twice" "typespec/specimen.py" \
  '                        + draw.svg(w, s * 1.5,
                                   draw.text_group(self.painter, before_p, s, 8, s * 1.1), "off")' \
  '                        + draw.svg(w, s * 1.5,
                                   draw.text_group(self.painter, after_p, s, 8, s * 1.1), "off")'

echo
echo "10. hygiene"
if git -C "$ROOT" rev-parse --git-dir >/dev/null 2>&1; then
  toplevel="$(git -C "$ROOT" rev-parse --show-toplevel)"
  if [ "$toplevel" = "$ROOT" ]; then ok "this directory is its own git repository"
  else bad "the git root is $toplevel, not this project"; fi

  hits=$(git -C "$ROOT" grep -In -e "/home/$(id -un)" -e "/Users/" -- . 2>/dev/null \
         | grep -v '^scripts/verify.sh' || true)
  if [ -z "$hits" ]; then ok "no absolute home paths in tracked files"
  else bad "home paths in tracked files"; printf '%s\n' "$hits" | head -4 | sed 's/^/        /'; fi

  keys=$(git -C "$ROOT" grep -In -E 'sk-[A-Za-z0-9]{20}|ghp_[A-Za-z0-9]{36}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10}' \
         -- . 2>/dev/null | grep -v '^scripts/verify.sh' || true)
  if [ -z "$keys" ]; then ok "no credential-shaped strings"
  else bad "possible credential"; printf '%s\n' "$keys" | head -3 | sed 's/^/        /'; fi

  # git and grep treat a file containing a NUL as binary and skip it, so the scan above would go
  # blind on one. Python reads every tracked file as bytes and says so.
  if python3 - <<'PY' >"$TMP/nul.log" 2>&1; then
import pathlib, subprocess, sys
files = subprocess.run(["git", "ls-files", "-z"], capture_output=True, check=True
                       ).stdout.split(b"\0")
hits = []
for name in files:
    if not name:
        continue
    path = pathlib.Path(name.decode())
    if not path.is_file():
        continue
    if b"\x00" in path.read_bytes():
        hits.append(str(path))
if hits:
    sys.exit(f"tracked files contain a NUL byte, which makes the secret scan blind to them: "
             f"{hits[:4]}")
count = len([f for f in files if f])
if count < 10:
    sys.exit(f"only {count} tracked files, so the secret scan above had almost nothing to read "
             f"and its silence means nothing. Commit the work before trusting it.")
print(f"{count} tracked files, none containing a NUL byte, so the secret scan above read all "
      f"of them")
PY
    sed 's/^/        /' "$TMP/nul.log"; ok "the secret scan was not blinded by a binary file"
  else bad "$(cat "$TMP/nul.log")"; fi

  fonts=$(git -C "$ROOT" ls-files | grep -iE '\.(ttf|otf|ttc|woff2?|pfb|pfa|dfont)$' || true)
  if [ -z "$fonts" ]; then ok "no font binaries committed, so no redistribution question arises"
  else bad "font binaries are tracked"; printf '%s\n' "$fonts" | head -4 | sed 's/^/        /'; fi

  big=$(git -C "$ROOT" ls-files -z | xargs -0 -r du -k 2>/dev/null \
        | awk '$1 > 1024 {print $1"K "$2}' || true)
  if [ -z "$big" ]; then ok "no tracked file over a megabyte"
  else bad "large tracked files"; printf '%s\n' "$big" | head -4 | sed 's/^/        /'; fi
else
  bad "not a git repository"
fi

# The page must not hedge against overflow, because that both hides the bug and makes the
# browser probe vacuous.
if grep -RIn 'overflow-x *: *hidden' typespec/ docs/ >/dev/null 2>&1; then
  bad "overflow-x: hidden appears in the styles, which would make the overflow probe vacuous"
else
  ok "no overflow-x: hidden anywhere, so the browser probe means something"
fi

echo
echo "    the README is a claim like any other"
if python3 - "$TEST_COUNT" <<'PY' >"$TMP/readme.log" 2>&1; then
import json, pathlib, re, sys
expected_tests = int(sys.argv[1])
readme = pathlib.Path("README.md").read_text(encoding="utf-8")
problems = []
if "## Status" not in readme:
    problems.append("no Status section")
if "VERIFY OK" not in readme:
    problems.append("the Status section does not contain the verify script's success line")
if "TODO" in readme:
    problems.append("the README still contains TODO")
for dash in ("—", "– "):
    if dash in readme:
        problems.append(f"an em or en dash is in the prose ({dash!r})")
        break
match = re.search(r"(\d+) tests passed, each with a negative control", readme)
if not match:
    problems.append("the README does not state the test count in the form the suite prints")
elif int(match.group(1)) != expected_tests:
    problems.append(f"the README says {match.group(1)} tests, the suite just ran {expected_tests}")
# Every measured number the README quotes must be in the facts the checker confirmed.
summary = json.loads(pathlib.Path("out/_index.json").read_text())
by_slug = {f["slug"]: f for f in summary["fonts"]}
for slug, x_height in re.findall(r"^\| `([a-z0-9-]+)` \|[^|]*\|[^|]*\|[^|]*\|[^|]*\| (\d+) \|",
                                 readme, re.M):
    if slug not in by_slug:
        problems.append(f"the README's table names {slug}, which is not in the built set")
    elif by_slug[slug]["x_height_measured"] != int(x_height):
        problems.append(f"the README says {slug} has a measured x-height of {x_height}, "
                        f"the checked facts say {by_slug[slug]['x_height_measured']}")
if problems:
    sys.exit("; ".join(problems))
print(f"Status section present with VERIFY OK, test count {expected_tests} matches, and every "
      f"x-height in the README's table matches the independently checked facts")
PY
  sed 's/^/        /' "$TMP/readme.log"; ok "the README states what actually happened"
else bad "$(cat "$TMP/readme.log")"; fi

echo
printf '%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ] || { echo "VERIFY FAILED"; exit 1; }
echo "VERIFY OK"
