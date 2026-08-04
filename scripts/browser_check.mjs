// Load the built pages in a real browser and assert on what the specimen must have produced.
//
// A page's numbers can be right in the JSON and absent from the DOM, and an SVG can be present
// and empty. So this asserts on rendered geometry: the waterfall's rows must actually grow, the
// glyph paths must have non-zero bounding boxes on screen, and the number the independent checker
// confirmed must be in the document.
//
// playwright-core is resolved without any absolute home path. If it cannot be found, or the
// browser cannot launch, this FAILS with an actionable message. It never skips.

import { existsSync, readdirSync, readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, "..");
const DOCS = join(REPO, "docs");

let pass = 0;
let fail = 0;
const ok = (m) => { console.log(`  ok    ${m}`); pass++; };
const bad = (m) => { console.log(`  FAIL  ${m}`); fail++; };

// --- find playwright-core ---------------------------------------------------
function findPlaywright() {
  const tried = [];
  const candidates = [];
  if (process.env.TYPESPEC_PLAYWRIGHT_CORE) {
    candidates.push(process.env.TYPESPEC_PLAYWRIGHT_CORE);
  }
  candidates.push(join(REPO, "node_modules", "playwright-core"));
  // Sibling projects, relative to this repository rather than to any user's home directory.
  const siblingRoot = resolve(REPO, "..");
  if (existsSync(siblingRoot)) {
    for (const name of readdirSync(siblingRoot).sort()) {
      candidates.push(join(siblingRoot, name, "node_modules", "playwright-core"));
    }
  }
  for (const dir of candidates) {
    tried.push(dir);
    if (existsSync(join(dir, "package.json"))) return { dir, tried };
  }
  return { dir: null, tried };
}

const { dir: pwDir, tried } = findPlaywright();
if (!pwDir) {
  console.error("playwright-core was not found. This check is FAILING, not skipping.\n");
  console.error("Fix it with either of:");
  console.error("  npm install --no-save playwright-core   (in this repository)");
  console.error("  TYPESPEC_PLAYWRIGHT_CORE=/path/to/playwright-core bash scripts/verify.sh\n");
  console.error(`Looked in ${tried.length} places, starting with ${tried[0]}`);
  console.error("\nWithout it the rest of the suite still covers the font parsing, the");
  console.error("independent re-derivation and the page's text, but nothing confirms the");
  console.error("pages render, which is the whole point of a specimen.");
  process.exit(2);
}

const require = createRequire(join(pwDir, "package.json"));
const { chromium } = require(pwDir);

// --- launch, and prove it launched -----------------------------------------
let browser;
try {
  browser = await chromium.launch();
} catch (err) {
  console.error("the browser did not launch, so nothing below was checked:\n" + err.message);
  console.error("\nInstall a Chromium build for playwright-core, for example with");
  console.error("  npx playwright install chromium");
  process.exit(2);
}
const version = browser.version();
if (!version) {
  console.error("chromium reported no version, so this is not a working browser");
  process.exit(2);
}
ok(`chromium ${version} launched from ${pwDir.replace(REPO, ".")}`);

const summary = JSON.parse(readFileSync(join(REPO, "out", "_index.json"), "utf8"));
const context = await browser.newContext();
const requests = [];
context.on("request", (r) => requests.push(r.url()));

// Every navigation asserts page identity before anything is measured, because the browser may be
// shared with another agent's session.
async function open(page, file, expectTitle) {
  const url = pathToFileURL(join(DOCS, file)).href;
  const response = await page.goto(url, { waitUntil: "load" });
  if (!response && !page.url().startsWith("file:")) throw new Error(`did not load ${file}`);
  const title = await page.title();
  if (!title.includes(expectTitle)) {
    throw new Error(`loaded ${file} but the title is "${title}", expected to contain `
      + `"${expectTitle}". The browser may have been navigated by something else.`);
  }
  return title;
}

const page = await context.newPage();

// --- index -----------------------------------------------------------------
try {
  await page.setViewportSize({ width: 1280, height: 900 });
  await open(page, "index.html", "Type specimens");
  ok("index.html loads and identifies itself");
} catch (err) {
  bad(`index.html: ${err.message}`);
}

// The comparison table must carry the measured numbers, read out of the live DOM.
try {
  const text = await page.evaluate(() => document.body.innerText);
  const missing = [];
  for (const f of summary.fonts) {
    if (!text.includes(String(f.x_height_measured))) missing.push(`${f.slug} x-height`);
    if (!text.includes(String(f.codepoint_count))) missing.push(`${f.slug} codepoints`);
  }
  if (missing.length) bad(`the index text is missing: ${missing.join(", ")}`);
  else ok(`the index carries every font's measured x-height and codepoint count (${summary.fonts.length} fonts)`);
} catch (err) {
  bad(`reading the index text: ${err.message}`);
}

// A font with no sxHeight must be shown as absent rather than given a number.
try {
  const absentCount = summary.fonts.filter((f) => f.x_height_declared === null).length;
  const shown = await page.evaluate(() =>
    Array.from(document.querySelectorAll("table i")).map((el) => el.textContent.trim()));
  const absentCells = shown.filter((t) => t === "absent").length;
  if (absentCount === 0) bad("no font in the set lacks sxHeight, so this check proves nothing");
  else if (absentCells < absentCount * 2) {
    bad(`${absentCount} fonts lack sxHeight and sCapHeight, but the table marks only `
      + `${absentCells} cells absent`);
  } else ok(`${absentCells} table cells say "absent" for the ${absentCount} fonts whose OS/2 `
    + `table is too old to carry x-height`);
} catch (err) {
  bad(`checking the absent markers: ${err.message}`);
}

// --- one full specimen page ------------------------------------------------
const target = summary.fonts.find((f) => f.slug === "lato") || summary.fonts[0];
try {
  await open(page, `${target.slug}.html`, target.family);
  ok(`${target.slug}.html loads and identifies itself`);
} catch (err) {
  bad(`${target.slug}.html: ${err.message}`);
}

// Glyph outlines really rendered, with real geometry rather than empty elements.
try {
  const geometry = await page.evaluate(() => {
    const paths = Array.from(document.querySelectorAll("svg path"));
    let drawn = 0;
    let totalCommands = 0;
    let biggest = 0;
    for (const p of paths) {
      const d = p.getAttribute("d") || "";
      totalCommands += (d.match(/[MLCQHVZ]/g) || []).length;
      const box = p.getBoundingClientRect();
      if (box.width > 0.5 && box.height > 0.5) drawn++;
      biggest = Math.max(biggest, box.height);
    }
    return { count: paths.length, drawn, totalCommands, biggest };
  });
  if (geometry.count < 200) bad(`only ${geometry.count} path elements on the page`);
  else if (geometry.drawn < geometry.count * 0.9) {
    bad(`${geometry.count} paths but only ${geometry.drawn} have a non-empty box on screen`);
  } else if (geometry.totalCommands < 5000) {
    bad(`only ${geometry.totalCommands} path commands, the outlines look empty`);
  } else if (geometry.biggest < 40) {
    bad(`the tallest rendered glyph is ${geometry.biggest.toFixed(1)}px, nothing is at size`);
  } else {
    ok(`${geometry.count} glyph paths drawn, ${geometry.totalCommands} path commands, `
      + `tallest ${geometry.biggest.toFixed(0)}px`);
  }
} catch (err) {
  bad(`measuring the outlines: ${err.message}`);
}

// The waterfall must actually be a waterfall: rows rising in size, measured on screen.
try {
  const heights = await page.evaluate(() => {
    const svg = document.querySelector("svg.waterfall");
    if (!svg) return null;
    return Array.from(svg.querySelectorAll("g")).map((g) => g.getBoundingClientRect().height);
  });
  if (!heights) bad("no waterfall svg on the page");
  else if (heights.length < 5) bad(`the waterfall has only ${heights.length} rows`);
  else {
    let rising = true;
    for (let i = 1; i < heights.length; i++) if (heights[i] <= heights[i - 1]) rising = false;
    const ratio = heights[heights.length - 1] / heights[0];
    if (!rising) bad(`the waterfall rows do not rise: ${heights.map((h) => h.toFixed(0)).join(", ")}`);
    else if (ratio < 4) bad(`the waterfall spans only ${ratio.toFixed(1)}x from smallest to largest`);
    else ok(`the waterfall rises across ${heights.length} rows, `
      + `${heights[0].toFixed(0)}px to ${heights[heights.length - 1].toFixed(0)}px on screen`);
  }
} catch (err) {
  bad(`measuring the waterfall: ${err.message}`);
}

// The metrics diagram's rules must land where the measured numbers say they do. This is the
// check that connects the drawing to the measurement rather than trusting the caption.
try {
  const result = await page.evaluate(() => {
    const svg = document.querySelector("svg.diagram");
    if (!svg) return { error: "no diagram" };
    const lines = Array.from(svg.querySelectorAll("line.rule.measured"));
    const labels = Array.from(svg.querySelectorAll("text.lbl.measured"))
      .map((t) => t.textContent.trim());
    const ys = lines.map((l) => Number(l.getAttribute("y1")));
    return { labels, ys, viewBox: svg.getAttribute("viewBox") };
  });
  if (result.error) bad(result.error);
  else {
    const baseline = result.labels.findIndex((t) => t.startsWith("baseline"));
    const xh = result.labels.findIndex((t) => t.startsWith("x_height"));
    const cap = result.labels.findIndex((t) => t.startsWith("cap_height"));
    const desc = result.labels.findIndex((t) => t.startsWith("descender"));
    if (baseline < 0 || xh < 0 || cap < 0 || desc < 0) {
      bad(`the diagram is missing rules: ${result.labels.join(" | ")}`);
    } else if (!(result.ys[cap] < result.ys[xh] && result.ys[xh] < result.ys[baseline]
                 && result.ys[baseline] < result.ys[desc])) {
      bad(`the diagram's rules are out of order: ${JSON.stringify(result.ys)}`);
    } else {
      const capValue = Number(result.labels[cap].split(" ").pop());
      const xhValue = Number(result.labels[xh].split(" ").pop());
      if (capValue !== target.cap_height_measured || xhValue !== target.x_height_measured) {
        bad(`the diagram labels say cap ${capValue} x-height ${xhValue}, the checked facts say `
          + `${target.cap_height_measured} and ${target.x_height_measured}`);
      } else {
        ok(`the diagram's rules sit in the right order and carry the checked values `
          + `(cap ${capValue}, x-height ${xhValue})`);
      }
    }
  }
} catch (err) {
  bad(`measuring the diagram: ${err.message}`);
}

// --- overflow, at desktop and at a narrow viewport -------------------------
async function overflowOffenders() {
  return page.evaluate(() => {
    const limit = document.documentElement.clientWidth;
    const offenders = [];
    // Content scrolling inside its own box is correct, so an ancestor with overflow-x auto or
    // scroll excuses a wide child. overflow-x hidden does NOT excuse anything here: it would
    // hide a real overflow and make this probe vacuous.
    const inScroller = (el) => {
      for (let p = el.parentElement; p; p = p.parentElement) {
        const ox = getComputedStyle(p).overflowX;
        if (ox === "auto" || ox === "scroll") return true;
      }
      return false;
    };
    for (const el of document.querySelectorAll("body *")) {
      if (inScroller(el)) continue;
      const box = el.getBoundingClientRect();
      if (box.width === 0 && box.height === 0) continue;
      if (box.right > limit + 1 || box.left < -1) {
        const cls = el.getAttribute("class") || "-";
        offenders.push(`${el.tagName.toLowerCase()}.${cls} `
          + `right=${box.right.toFixed(0)} limit=${limit}`);
      }
    }
    return {
      offenders: offenders.slice(0, 5),
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: limit,
    };
  });
}

for (const width of [1280, 390]) {
  try {
    await page.setViewportSize({ width, height: 900 });
    await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => r())));
    const r = await overflowOffenders();
    if (r.offenders.length) {
      bad(`at ${width}px, ${r.offenders.length}+ elements escape the page: ${r.offenders.join("; ")}`);
    } else if (r.scrollWidth > r.clientWidth + 1) {
      bad(`at ${width}px the document scrolls sideways `
        + `(${r.scrollWidth} > ${r.clientWidth}) with no element to blame, which means the probe `
        + `is looking in the wrong place`);
    } else {
      ok(`at ${width}px nothing escapes the page and the body does not scroll sideways`);
    }
  } catch (err) {
    bad(`overflow at ${width}px: ${err.message}`);
  }
}

// Wide content must be reachable rather than clipped: the scrollers must really scroll.
try {
  await page.setViewportSize({ width: 390, height: 900 });
  const scrollers = await page.evaluate(() => {
    const out = { total: 0, scrollable: 0 };
    for (const el of document.querySelectorAll(".scroll")) {
      out.total++;
      if (el.scrollWidth > el.clientWidth + 1) out.scrollable++;
    }
    return out;
  });
  if (scrollers.total === 0) bad("no .scroll containers on the page");
  else if (scrollers.scrollable === 0) {
    bad(`${scrollers.total} scroll containers and none of them overflow at 390px, so the `
      + `specimen is not being shown at its intrinsic size`);
  } else {
    ok(`${scrollers.scrollable} of ${scrollers.total} scroll containers hold content wider than `
      + `a 390px viewport, reachable by scrolling that box`);
  }
} catch (err) {
  bad(`checking the scrollers: ${err.message}`);
}

// --- links ------------------------------------------------------------------
try {
  await page.setViewportSize({ width: 1280, height: 900 });
  await open(page, "index.html", "Type specimens");
  const links = await page.evaluate(() =>
    Array.from(document.querySelectorAll("a[href]")).map((a) => a.getAttribute("href")));
  const broken = [];
  let internal = 0;
  for (const href of links) {
    if (/^https?:/.test(href)) continue;
    internal++;
    if (!existsSync(join(DOCS, href.split("#")[0]))) broken.push(href);
  }
  if (broken.length) bad(`broken internal links: ${broken.join(", ")}`);
  else if (internal < summary.fonts.length) {
    bad(`only ${internal} internal links for ${summary.fonts.length} fonts`);
  } else ok(`${internal} internal links all resolve to files that exist`);
} catch (err) {
  bad(`checking links: ${err.message}`);
}

// --- no network -------------------------------------------------------------
const offsite = requests.filter((u) => !u.startsWith("file:") && !u.startsWith("data:"));
if (offsite.length) bad(`the pages requested ${offsite.length} off-site resources: `
  + offsite.slice(0, 3).join(", "));
else ok(`${requests.length} requests, all file: or data:, so the pages need no network`);

await browser.close();
console.log(`${pass} browser checks passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
