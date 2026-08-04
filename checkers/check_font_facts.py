#!/usr/bin/env python3
"""Re-derive every font fact the specimen prints, from the font's bytes, independently.

This file deliberately imports nothing from ``typespec`` and nothing from ``fontTools``. It reads
the sfnt container with ``struct`` and answers, for itself:

  * unitsPerEm, from head
  * OS/2 table version, and whether sxHeight and sCapHeight exist in it at all
  * hhea ascender, descender and lineGap
  * every codepoint in the cmap, from formats 0, 4, 6 and 12
  * the bounding box of a named glyph, from glyf for TrueType outlines and by interpreting Type 2
    charstrings for CFF outlines
  * advance widths, from hmtx
  * GSUB and GPOS feature tags, and the raw decipoint values in the GPOS size feature

Then it compares those answers against the JSON the generator wrote. A validator that shares code
with the thing it validates inherits its bugs; this one shares no line of it.

``checkers/check_independence.py`` proves the no-shared-code claim by walking this file's import
graph with ``ast`` rather than taking the sentence above on trust.

    python3 checkers/check_font_facts.py out/*.json
"""

import json
import os
import struct
import sys


# ---------------------------------------------------------------------------
# sfnt container

class Sfnt:
    def __init__(self, path):
        with open(path, "rb") as fh:
            self.data = fh.read()
        tag = self.data[:4]
        if tag == b"ttcf":
            count, = struct.unpack(">I", self.data[8:12])
            if count < 1:
                raise ValueError("empty font collection")
            offset, = struct.unpack(">I", self.data[12:16])
        elif tag in (b"\x00\x01\x00\x00", b"OTTO", b"true"):
            offset = 0
        else:
            raise ValueError(f"not an sfnt font: leading bytes {tag!r}")
        num_tables, = struct.unpack(">H", self.data[offset + 4:offset + 6])
        self.tables = {}
        pos = offset + 12
        for _ in range(num_tables):
            name, _csum, off, length = struct.unpack(">4sIII", self.data[pos:pos + 16])
            self.tables[name.decode("latin-1")] = (off, length)
            pos += 16

    def table(self, name):
        if name not in self.tables:
            return None
        off, length = self.tables[name]
        return self.data[off:off + length]

    def has(self, name):
        return name in self.tables


def u16(b, o):
    return struct.unpack_from(">H", b, o)[0]


def s16(b, o):
    return struct.unpack_from(">h", b, o)[0]


def u32(b, o):
    return struct.unpack_from(">I", b, o)[0]


def u8(b, o):
    return b[o]


# ---------------------------------------------------------------------------
# metric tables

def head_facts(sfnt):
    head = sfnt.table("head")
    return {"units_per_em": u16(head, 18),
            "index_to_loc_format": s16(head, 50)}


def hhea_facts(sfnt):
    hhea = sfnt.table("hhea")
    return {"ascender": s16(hhea, 4), "descender": s16(hhea, 6),
            "line_gap": s16(hhea, 8), "num_h_metrics": u16(hhea, 34)}


# OS/2 field offsets. sxHeight and sCapHeight arrive at version 2; a version 0 or 1 table is
# simply shorter and the fields are not there to read.
def os2_facts(sfnt):
    os2 = sfnt.table("OS/2")
    if os2 is None:
        return {"present": False}
    version = u16(os2, 0)
    out = {"present": True, "version": version,
           "typo_ascender": s16(os2, 68), "typo_descender": s16(os2, 70),
           "typo_line_gap": s16(os2, 72),
           "win_ascent": u16(os2, 74), "win_descent": u16(os2, 76)}
    if version >= 2 and len(os2) >= 90:
        out["x_height"] = s16(os2, 86)
        out["cap_height"] = s16(os2, 88)
    else:
        out["x_height"] = None
        out["cap_height"] = None
    return out


# ---------------------------------------------------------------------------
# cmap

def cmap_codepoints(sfnt):
    """Every codepoint mapped to a non-zero glyph id by the best unicode subtable."""
    cmap = sfnt.table("cmap")
    n = u16(cmap, 2)
    best, best_rank = None, -1
    for i in range(n):
        pid = u16(cmap, 4 + i * 8)
        eid = u16(cmap, 6 + i * 8)
        off = u32(cmap, 8 + i * 8)
        rank = {(3, 10): 5, (0, 6): 4, (0, 4): 4, (3, 1): 3,
                (0, 3): 3, (0, 2): 2, (0, 1): 2, (0, 0): 2}.get((pid, eid), -1)
        if rank > best_rank:
            best, best_rank = off, rank
    if best is None:
        raise ValueError("no unicode cmap subtable")
    return parse_cmap_subtable(cmap, best)


def parse_cmap_subtable(cmap, off):
    fmt = u16(cmap, off)
    out = {}
    if fmt == 0:
        for cp in range(256):
            gid = u8(cmap, off + 6 + cp)
            if gid:
                out[cp] = gid
    elif fmt == 4:
        seg2 = u16(cmap, off + 6)
        seg = seg2 // 2
        ends = off + 14
        starts = ends + seg2 + 2
        deltas = starts + seg2
        ranges = deltas + seg2
        for i in range(seg):
            end = u16(cmap, ends + i * 2)
            start = u16(cmap, starts + i * 2)
            delta = s16(cmap, deltas + i * 2)
            range_off = u16(cmap, ranges + i * 2)
            if start > end:
                continue
            for cp in range(start, min(end, 0xFFFF) + 1):
                if range_off == 0:
                    gid = (cp + delta) & 0xFFFF
                else:
                    addr = ranges + i * 2 + range_off + (cp - start) * 2
                    if addr + 2 > len(cmap):
                        continue
                    gid = u16(cmap, addr)
                    if gid:
                        gid = (gid + delta) & 0xFFFF
                if gid:
                    out[cp] = gid
    elif fmt == 6:
        first = u16(cmap, off + 6)
        count = u16(cmap, off + 8)
        for i in range(count):
            gid = u16(cmap, off + 10 + i * 2)
            if gid:
                out[first + i] = gid
    elif fmt == 12:
        groups = u32(cmap, off + 12)
        for i in range(groups):
            base = off + 16 + i * 12
            start = u32(cmap, base)
            end = u32(cmap, base + 4)
            gid = u32(cmap, base + 8)
            for j in range(end - start + 1):
                if gid + j:
                    out[start + j] = gid + j
    else:
        raise ValueError(f"cmap subtable format {fmt} not handled by this checker")
    return out


def to_ranges(codepoints):
    out = []
    for cp in sorted(codepoints):
        if out and cp == out[-1][1] + 1:
            out[-1][1] = cp
        else:
            out.append([cp, cp])
    return [list(r) for r in out]


# ---------------------------------------------------------------------------
# glyph outlines: glyf

def glyf_bbox(sfnt, gid, depth=0):
    """Bounding box of a glyph from the glyf table, resolving composites."""
    if depth > 5:
        raise ValueError("composite glyph nested too deeply")
    head = head_facts(sfnt)
    loca = sfnt.table("loca")
    glyf = sfnt.table("glyf")
    if head["index_to_loc_format"] == 0:
        start = u16(loca, gid * 2) * 2
        end = u16(loca, gid * 2 + 2) * 2
    else:
        start = u32(loca, gid * 4)
        end = u32(loca, gid * 4 + 4)
    if end <= start:
        return None                                   # a blank glyph, such as space
    n_contours = s16(glyf, start)
    if n_contours >= 0:
        # A simple glyph carries its own box in its header, which is the value a rasteriser uses.
        return (s16(glyf, start + 2), s16(glyf, start + 4),
                s16(glyf, start + 6), s16(glyf, start + 8))
    # Composite. The header box is authoritative in a well formed font, but this checker
    # recomputes it from the components so a wrong header cannot hide.
    boxes = []
    pos = start + 10
    while True:
        flags = u16(glyf, pos)
        comp_gid = u16(glyf, pos + 2)
        pos += 4
        if flags & 0x0001:                            # ARG_1_AND_2_ARE_WORDS
            dx, dy = s16(glyf, pos), s16(glyf, pos + 2)
            pos += 4
        else:
            dx = struct.unpack_from(">b", glyf, pos)[0]
            dy = struct.unpack_from(">b", glyf, pos + 1)[0]
            pos += 2
        if not flags & 0x0002:                        # ARGS_ARE_XY_VALUES
            dx = dy = 0
        scale_x = scale_y = 1.0
        if flags & 0x0008:                            # WE_HAVE_A_SCALE
            scale_x = scale_y = f2dot14(glyf, pos)
            pos += 2
        elif flags & 0x0040:                          # X_AND_Y_SCALE
            scale_x, scale_y = f2dot14(glyf, pos), f2dot14(glyf, pos + 2)
            pos += 4
        elif flags & 0x0080:                          # TWO_BY_TWO
            scale_x, scale_y = f2dot14(glyf, pos), f2dot14(glyf, pos + 6)
            pos += 8
        sub = glyf_bbox(sfnt, comp_gid, depth + 1)
        if sub is not None:
            xs = [sub[0] * scale_x + dx, sub[2] * scale_x + dx]
            ys = [sub[1] * scale_y + dy, sub[3] * scale_y + dy]
            boxes.append((min(xs), min(ys), max(xs), max(ys)))
        if not flags & 0x0020:                        # MORE_COMPONENTS
            break
    if not boxes:
        return None
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def f2dot14(b, o):
    return s16(b, o) / 16384.0


# ---------------------------------------------------------------------------
# glyph outlines: CFF Type 2 charstrings

class CFF:
    """Just enough CFF to walk a charstring and take its bounding box."""

    def __init__(self, data):
        self.data = data
        hdr_size = data[2]
        pos = hdr_size
        pos = self._skip_index(pos)                      # Name INDEX
        top_dicts, pos = self._read_index(pos)           # Top DICT INDEX
        pos = self._skip_index(pos)                      # String INDEX
        self.gsubrs, pos = self._read_index(pos)         # Global Subr INDEX
        top = self._parse_dict(top_dicts[0])
        self.charstrings, _ = self._read_index(top[17][0])
        self.subrs = []
        self.nominal_width = 0
        self.default_width = 0
        if 18 in top:                                    # Private DICT size, offset
            size, offset = int(top[18][0]), int(top[18][1])
            private = self._parse_dict(self.data[offset:offset + size])
            self.default_width = private.get(20, [0])[0]
            self.nominal_width = private.get(21, [0])[0]
            if 19 in private:
                self.subrs, _ = self._read_index(offset + int(private[19][0]))
        self.is_cid = 1230 in top
        self.fd_select = None
        self.fd_subrs = []
        if self.is_cid and 1237 in top and 1236 in top:
            self.fd_select = self._parse_fdselect(int(top[1237][0]))
            fd_dicts, _ = self._read_index(int(top[1236][0]))
            for raw in fd_dicts:
                fd = self._parse_dict(raw)
                subrs = []
                if 18 in fd:
                    size, offset = int(fd[18][0]), int(fd[18][1])
                    priv = self._parse_dict(self.data[offset:offset + size])
                    if 19 in priv:
                        subrs, _ = self._read_index(offset + int(priv[19][0]))
                self.fd_subrs.append(subrs)

    def _read_index(self, pos):
        count = u16(self.data, pos)
        if count == 0:
            return [], pos + 2
        off_size = self.data[pos + 2]
        offsets = []
        base = pos + 3
        for i in range(count + 1):
            value = 0
            for j in range(off_size):
                value = (value << 8) | self.data[base + i * off_size + j]
            offsets.append(value)
        data_base = base + (count + 1) * off_size - 1
        items = [self.data[data_base + offsets[i]:data_base + offsets[i + 1]]
                 for i in range(count)]
        return items, data_base + offsets[-1]

    def _skip_index(self, pos):
        return self._read_index(pos)[1]

    def _parse_dict(self, raw):
        out, operands, i = {}, [], 0
        while i < len(raw):
            b0 = raw[i]
            if b0 <= 21:
                op = b0
                i += 1
                if b0 == 12:
                    op = 1200 + raw[i]
                    i += 1
                out[op] = operands
                operands = []
            elif b0 == 28:
                operands.append(struct.unpack_from(">h", raw, i + 1)[0]); i += 3
            elif b0 == 29:
                operands.append(struct.unpack_from(">i", raw, i + 1)[0]); i += 5
            elif b0 == 30:
                value, i = self._real(raw, i + 1)
                operands.append(value)
            elif 32 <= b0 <= 246:
                operands.append(b0 - 139); i += 1
            elif 247 <= b0 <= 250:
                operands.append((b0 - 247) * 256 + raw[i + 1] + 108); i += 2
            elif 251 <= b0 <= 254:
                operands.append(-(b0 - 251) * 256 - raw[i + 1] - 108); i += 2
            else:
                i += 1
        return out

    @staticmethod
    def _real(raw, i):
        nibbles = "0123456789.EE?-?"
        text = ""
        while i < len(raw):
            b = raw[i]
            i += 1
            for nib in (b >> 4, b & 15):
                if nib == 15:
                    return float(text or "0"), i
                if nib == 12:
                    text += "E-"
                else:
                    text += nibbles[nib]
        return float(text or "0"), i

    def _parse_fdselect(self, pos):
        fmt = self.data[pos]
        select = {}
        if fmt == 0:
            for gid in range(len(self.charstrings)):
                select[gid] = self.data[pos + 1 + gid]
        elif fmt == 3:
            n_ranges = u16(self.data, pos + 1)
            base = pos + 3
            for i in range(n_ranges):
                first = u16(self.data, base + i * 3)
                fd = self.data[base + i * 3 + 2]
                nxt = u16(self.data, base + (i + 1) * 3)
                for gid in range(first, nxt):
                    select[gid] = fd
        return select

    @staticmethod
    def _bias(subrs):
        if len(subrs) < 1240:
            return 107
        if len(subrs) < 33900:
            return 1131
        return 32768

    def bbox(self, gid):
        subrs = self.subrs
        if self.fd_select is not None:
            subrs = self.fd_subrs[self.fd_select.get(gid, 0)]
        state = _T2State(self, subrs)
        state.run(self.charstrings[gid])
        if state.min_x is None:
            return None
        return (state.min_x, state.min_y, state.max_x, state.max_y)


class _T2State:
    """A Type 2 charstring interpreter that tracks only the pen path's extent."""

    def __init__(self, cff, subrs):
        self.cff = cff
        self.subrs = subrs
        self.gsubrs = cff.gsubrs
        self.stack = []
        self.x = self.y = 0.0
        self.n_stems = 0
        self.width_parsed = False
        self.min_x = self.min_y = self.max_x = self.max_y = None
        self.depth = 0
        self.trans = []

    def point(self):
        if self.min_x is None:
            self.min_x = self.max_x = self.x
            self.min_y = self.max_y = self.y
        else:
            self.min_x = min(self.min_x, self.x)
            self.max_x = max(self.max_x, self.x)
            self.min_y = min(self.min_y, self.y)
            self.max_y = max(self.max_y, self.y)

    def _stems(self, even_is_width=True):
        count = len(self.stack)
        if not self.width_parsed and count % 2 == 1 and even_is_width:
            self.stack.pop(0)
        self.width_parsed = True
        self.n_stems += len(self.stack) // 2
        self.stack = []

    def run(self, code):
        self.depth += 1
        if self.depth > 10:
            raise ValueError("charstring recursion too deep")
        i = 0
        while i < len(code):
            b0 = code[i]
            if b0 >= 32 or b0 == 28:
                if b0 == 28:
                    self.stack.append(struct.unpack_from(">h", code, i + 1)[0]); i += 3
                elif b0 <= 246:
                    self.stack.append(b0 - 139); i += 1
                elif b0 <= 250:
                    self.stack.append((b0 - 247) * 256 + code[i + 1] + 108); i += 2
                elif b0 <= 254:
                    self.stack.append(-(b0 - 251) * 256 - code[i + 1] - 108); i += 2
                else:
                    self.stack.append(struct.unpack_from(">i", code, i + 1)[0] / 65536.0); i += 5
                continue
            i += 1
            if b0 in (1, 3, 18, 23):                       # h/vstem, hstemhm, vstemhm
                self._stems()
            elif b0 in (19, 20):                           # hintmask, cntrmask
                self._stems()
                i += (self.n_stems + 7) // 8
            elif b0 == 21:                                 # rmoveto
                if len(self.stack) > 2 and not self.width_parsed:
                    self.stack.pop(0)
                self.width_parsed = True
                self.x += self.stack[0]; self.y += self.stack[1]
                self.point(); self.stack = []
            elif b0 == 22:                                 # hmoveto
                if len(self.stack) > 1 and not self.width_parsed:
                    self.stack.pop(0)
                self.width_parsed = True
                self.x += self.stack[0]; self.point(); self.stack = []
            elif b0 == 4:                                  # vmoveto
                if len(self.stack) > 1 and not self.width_parsed:
                    self.stack.pop(0)
                self.width_parsed = True
                self.y += self.stack[0]; self.point(); self.stack = []
            elif b0 == 5:                                  # rlineto
                for j in range(0, len(self.stack) - 1, 2):
                    self.x += self.stack[j]; self.y += self.stack[j + 1]; self.point()
                self.stack = []
            elif b0 in (6, 7):                             # hlineto, vlineto
                horizontal = (b0 == 6)
                for value in self.stack:
                    if horizontal:
                        self.x += value
                    else:
                        self.y += value
                    self.point()
                    horizontal = not horizontal
                self.stack = []
            elif b0 == 8:                                  # rrcurveto
                for j in range(0, len(self.stack) - 5, 6):
                    self._curve(*self.stack[j:j + 6])
                self.stack = []
            elif b0 == 24:                                 # rcurveline
                j = 0
                while len(self.stack) - j >= 8:
                    self._curve(*self.stack[j:j + 6]); j += 6
                self.x += self.stack[j]; self.y += self.stack[j + 1]; self.point()
                self.stack = []
            elif b0 == 25:                                 # rlinecurve
                j = 0
                while len(self.stack) - j >= 8:
                    self.x += self.stack[j]; self.y += self.stack[j + 1]; self.point(); j += 2
                self._curve(*self.stack[j:j + 6])
                self.stack = []
            elif b0 in (26, 27):                           # vvcurveto, hhcurveto
                j = 0
                d1 = 0
                if len(self.stack) % 4 == 1:
                    d1 = self.stack[0]; j = 1
                while j + 3 < len(self.stack):
                    a, b, c, d = self.stack[j:j + 4]
                    if b0 == 26:
                        self._curve(d1, a, b, c, 0, d)
                    else:
                        self._curve(a, d1, b, c, d, 0)
                    d1 = 0
                    j += 4
                self.stack = []
            elif b0 in (30, 31):                           # vhcurveto, hvcurveto
                horizontal = (b0 == 31)
                j = 0
                while j + 3 < len(self.stack):
                    last = (len(self.stack) - j == 5)
                    a, b, c, d = self.stack[j:j + 4]
                    extra = self.stack[j + 4] if last else 0
                    if horizontal:
                        self._curve(a, 0, b, c, extra, d)
                    else:
                        self._curve(0, a, b, c, d, extra)
                    horizontal = not horizontal
                    j += 4
                self.stack = []
            elif b0 == 10:                                 # callsubr
                idx = int(self.stack.pop()) + CFF._bias(self.subrs)
                self.run(self.subrs[idx])
            elif b0 == 29:                                 # callgsubr
                idx = int(self.stack.pop()) + CFF._bias(self.gsubrs)
                self.run(self.gsubrs[idx])
            elif b0 == 11:                                 # return
                self.depth -= 1
                return
            elif b0 == 14:                                 # endchar
                self.width_parsed = True
                self.stack = []
                self.depth -= 1
                return
            elif b0 == 12:                                 # escape
                b1 = code[i]; i += 1
                if b1 == 35:                               # flex
                    self._curve(*self.stack[0:6]); self._curve(*self.stack[6:12])
                elif b1 == 34:                             # hflex
                    dx1, dx2, dy2, dx3, dx4, dx5, dx6 = self.stack[:7]
                    self._curve(dx1, 0, dx2, dy2, dx3, 0)
                    self._curve(dx4, 0, dx5, -dy2, dx6, 0)
                elif b1 == 36:                             # hflex1
                    dx1, dy1, dx2, dy2, dx3, dx4, dx5, dy5, dx6 = self.stack[:9]
                    self._curve(dx1, dy1, dx2, dy2, dx3, 0)
                    self._curve(dx4, 0, dx5, dy5, dx6, -(dy1 + dy2 + dy5))
                elif b1 == 37:                             # flex1
                    d = self.stack[:11]
                    dx = d[0] + d[2] + d[4] + d[6] + d[8]
                    dy = d[1] + d[3] + d[5] + d[7] + d[9]
                    self._curve(*d[0:6])
                    if abs(dx) > abs(dy):
                        self._curve(d[6], d[7], d[8], d[9], d[10], -(d[1] + d[3] + d[5]
                                                                     + d[7] + d[9]))
                    else:
                        self._curve(d[6], d[7], d[8], d[9],
                                    -(d[0] + d[2] + d[4] + d[6] + d[8]), d[10])
                self.stack = []
            else:
                self.stack = []
        self.depth -= 1

    def _curve(self, dx1, dy1, dx2, dy2, dx3, dy3):
        """Extent of one cubic segment.

        Taking the four control points as the box would over-report, and taking only the ends
        would under-report. The true extremes are the endpoints plus any turning point inside
        0 < t < 1, found by solving B'(t) = 0 per axis.
        """
        x0, y0 = self.x, self.y
        x1, y1 = x0 + dx1, y0 + dy1
        x2, y2 = x1 + dx2, y1 + dy2
        x3, y3 = x2 + dx3, y2 + dy3
        self.x, self.y = x3, y3
        for axis, (p0, p1, p2, p3) in enumerate(((x0, x1, x2, x3), (y0, y1, y2, y3))):
            values = [p0, p3]
            # B'(t)/3 = (p1-p0)(1-t)^2 + 2(p2-p1)(1-t)t + (p3-p2)t^2
            #         = (a - 2b + c) t^2 + 2(b - a) t + a,  with a,b,c the successive deltas.
            a, b, c = p1 - p0, p2 - p1, p3 - p2
            for t in _roots(a - 2 * b + c, 2 * (b - a), a):
                if 0 < t < 1:
                    mt = 1 - t
                    values.append(mt ** 3 * p0 + 3 * mt * mt * t * p1
                                  + 3 * mt * t * t * p2 + t ** 3 * p3)
            lo, hi = min(values), max(values)
            if axis == 0:
                self.min_x = lo if self.min_x is None else min(self.min_x, lo)
                self.max_x = hi if self.max_x is None else max(self.max_x, hi)
            else:
                self.min_y = lo if self.min_y is None else min(self.min_y, lo)
                self.max_y = hi if self.max_y is None else max(self.max_y, hi)


def _roots(a, b, c):
    """Real roots of a t^2 + b t + c, guarding the degenerate linear case."""
    if abs(a) < 1e-12:
        if abs(b) < 1e-12:
            return []
        return [-c / b]
    disc = b * b - 4 * a * c
    if disc < 0:
        return []
    root = disc ** 0.5
    return [(-b + root) / (2 * a), (-b - root) / (2 * a)]


# ---------------------------------------------------------------------------
# hmtx, GSUB/GPOS features

def advance_width(sfnt, gid):
    hhea = hhea_facts(sfnt)
    hmtx = sfnt.table("hmtx")
    n = hhea["num_h_metrics"]
    if gid < n:
        return u16(hmtx, gid * 4)
    return u16(hmtx, (n - 1) * 4)


def feature_tags(sfnt, name):
    raw = sfnt.table(name)
    if raw is None:
        return []
    feature_list_off = u16(raw, 6)
    count = u16(raw, feature_list_off)
    tags = set()
    for i in range(count):
        tag = raw[feature_list_off + 2 + i * 6:feature_list_off + 6 + i * 6]
        tags.add(tag.decode("latin-1"))
    return sorted(tags)


def size_feature_raw(sfnt):
    """The GPOS size feature's parameters as the uint16 decipoints actually stored in the file."""
    raw = sfnt.table("GPOS")
    if raw is None:
        return None
    feature_list_off = u16(raw, 6)
    count = u16(raw, feature_list_off)
    for i in range(count):
        base = feature_list_off + 2 + i * 6
        tag = raw[base:base + 4].decode("latin-1")
        if tag != "size":
            continue
        feature_off = feature_list_off + u16(raw, base + 4)
        params_off = u16(raw, feature_off)
        if params_off == 0:
            continue
        p = feature_off + params_off
        return {"design_size": u16(raw, p), "subfamily_id": u16(raw, p + 2),
                "range_start": u16(raw, p + 6), "range_end": u16(raw, p + 8)}
    return None


# ---------------------------------------------------------------------------
# glyph name to gid, via post or cmap

def gid_for_char(sfnt, char):
    return cmap_codepoints(sfnt).get(ord(char))


def glyph_bbox(sfnt, gid):
    """Bounding box in font units, or ("unsupported", reason) when this checker cannot get one."""
    if sfnt.has("glyf"):
        return glyf_bbox(sfnt, gid)
    if sfnt.has("CFF "):
        return CFF(sfnt.table("CFF ")).bbox(gid)
    if sfnt.has("CFF2"):
        raise Unsupported("CFF2 outlines are not implemented by this checker")
    raise Unsupported("no glyf, CFF or CFF2 table")


def _close(mine, theirs, relative=1e-9):
    """Relative comparison for floating-point values.

    A fixed epsilon means one thing at 0.6 and something else entirely at 750, so the tolerance
    scales with the magnitude of the value being checked.
    """
    scale = max(abs(mine), abs(theirs), 1.0)
    return abs(mine - theirs) <= relative * scale


class Unsupported(Exception):
    """Raised where this checker genuinely cannot derive a value.

    It is deliberately not caught and turned into a pass. A check that cannot run must say so.
    """


# ---------------------------------------------------------------------------
# comparison

EXEMPLARS = {"x_height": "x", "cap_height": "H", "ascender": "b",
             "descender": "p", "figure_height": "1"}
EDGE = {"x_height": 3, "cap_height": 3, "ascender": 3, "descender": 1, "figure_height": 3}


def check_one(facts_path):
    with open(facts_path, encoding="utf-8") as fh:
        facts = json.load(fh)
    path = _locate(facts)
    problems, checks = [], 0
    sfnt = Sfnt(path)

    def compare(label, mine, theirs):
        nonlocal checks
        checks += 1
        if mine != theirs:
            problems.append(f"{label}: the generator says {theirs!r}, the bytes say {mine!r}")

    head = head_facts(sfnt)
    hhea = hhea_facts(sfnt)
    os2 = os2_facts(sfnt)
    d = facts["declared"]

    compare("units per em", head["units_per_em"], d["units_per_em"])
    compare("hhea ascender", hhea["ascender"], d["hhea_ascender"])
    compare("hhea descender", hhea["descender"], d["hhea_descender"])
    compare("hhea line gap", hhea["line_gap"], d["hhea_line_gap"])
    compare("OS/2 version", os2.get("version"), d["os2_version"])
    compare("OS/2 sxHeight", os2.get("x_height"), d["x_height"])
    compare("OS/2 sCapHeight", os2.get("cap_height"), d["cap_height"])
    compare("OS/2 sTypoAscender", os2.get("typo_ascender"), d["typo_ascender"])
    compare("OS/2 sTypoDescender", os2.get("typo_descender"), d["typo_descender"])
    compare("OS/2 usWinAscent", os2.get("win_ascent"), d["win_ascent"])
    compare("OS/2 usWinDescent", os2.get("win_descent"), d["win_descent"])

    cmap = cmap_codepoints(sfnt)
    compare("cmap codepoint count", len(cmap), facts["coverage"]["codepoint_count"])
    compare("cmap ranges", to_ranges(cmap.keys()),
            [list(r) for r in facts["coverage"]["ranges"]])

    # Measured metrics, re-derived from the outlines this checker parses itself.
    unsupported = []
    for measure, char in EXEMPLARS.items():
        claim = facts["measured"][measure]
        gid = cmap.get(ord(char))
        if gid is None:
            compare(f"{measure} availability", False, claim["available"])
            continue
        try:
            box = glyph_bbox(sfnt, gid)
        except Unsupported as exc:
            unsupported.append(f"{measure}: {exc}")
            continue
        if box is None:
            compare(f"{measure} availability", False, claim["available"])
            continue
        checks += 1
        if not claim["available"]:
            problems.append(f"{measure}: the generator reports it unavailable, but the outline "
                            f"of {char!r} has a bounding box")
            continue
        # Both derivations produce whole font units, so this is exact equality rather than a
        # tolerance. An absolute slack of a unit or two would be a place for a real disagreement
        # to hide, and measured across every font here the two agree to the unit already.
        mine = int(round(box[EDGE[measure]]))
        if mine != claim["value"]:
            problems.append(f"{measure}: the generator says {claim['value']}, "
                            f"the outline of {char!r} gives {mine}")
        mine_box = [int(round(v)) for v in box]
        if mine_box != list(claim["bbox"]):
            problems.append(f"{measure}: bounding box {claim['bbox']} from the generator, "
                            f"{mine_box} from the outline")
        checks += 1

    compare("GSUB feature tags", feature_tags(sfnt, "GSUB"),
            sorted(e["tag"] for e in facts["features"]["GSUB"]))
    compare("GPOS feature tags", feature_tags(sfnt, "GPOS"),
            sorted(e["tag"] for e in facts["features"]["GPOS"]))
    compare("legacy kern table present", sfnt.has("kern"), facts["has_legacy_kern_table"])
    compare("glyph count", u16(sfnt.table("maxp"), 4), facts["glyph_count"])
    compare("outline format", "glyf" if sfnt.has("glyf") else
            ("CFF2" if sfnt.has("CFF2") else ("CFF" if sfnt.has("CFF ") else "unknown")),
            facts["outline_format"])

    raw_size = size_feature_raw(sfnt)
    if raw_size is None:
        compare("size feature", None, facts["size_feature"])
    else:
        claim = facts["size_feature"]
        if claim is None:
            problems.append("size feature: the font has one and the generator reports none")
            checks += 1
        else:
            compare("size feature design size, decipoints",
                    raw_size["design_size"], claim["raw_decipoints"]["design_size"])
            compare("size feature range start, decipoints",
                    raw_size["range_start"], claim["raw_decipoints"]["range_start"])
            compare("size feature range end, decipoints",
                    raw_size["range_end"], claim["raw_decipoints"]["range_end"])
            # Points are decipoints over ten. A generator that divides twice fails here.
            for key in ("design_size", "range_start", "range_end"):
                checks += 1
                if not _close(raw_size[key] / 10.0, claim[key]):
                    problems.append(f"size feature {key} in points: the generator says "
                                    f"{claim[key]}, the bytes give {raw_size[key] / 10.0}")

    compare("file size in bytes", os.path.getsize(path), facts["file_bytes"])

    return {"font": facts.get("slug") or facts["file_name"], "path": path,
            "checks": checks, "problems": problems, "unsupported": unsupported}


def _locate(facts):
    """Find the font this facts file describes, and refuse to check a different file."""
    import hashlib
    candidates = [facts.get("source_path")] if facts.get("source_path") else []
    candidates += _search_paths(facts["file_name"])
    for path in candidates:
        if path and os.path.exists(path) and os.path.getsize(path) == facts["file_bytes"]:
            h = hashlib.sha256()
            with open(path, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 16), b""):
                    h.update(chunk)
            if h.hexdigest() == facts["file_sha256"]:
                return path
    raise SystemExit(
        f"cannot find the font {facts['file_name']!r} with sha256 {facts['file_sha256']} on this "
        f"machine, so its facts cannot be checked. Install the font packages named in fonts.json "
        f"and rebuild. This check is NOT being skipped, it is failing.")


def _search_paths(file_name):
    roots = ["/usr/share/fonts", "/usr/local/share/fonts", "/usr/share/texmf/fonts",
             os.path.expanduser("~/.fonts"), os.path.expanduser("~/.local/share/fonts")]
    out = []
    for root in roots:
        for dirpath, _dirnames, filenames in os.walk(root):
            if file_name in filenames:
                out.append(os.path.join(dirpath, file_name))
    return sorted(out)


def fvar_defaults(sfnt):
    """Axis tag to default value, straight out of fvar."""
    raw = sfnt.table("fvar")
    if raw is None:
        return None
    axes_offset = u16(raw, 4)
    axis_count = u16(raw, 8)
    axis_size = u16(raw, 10)
    out = {}
    for i in range(axis_count):
        base = axes_offset + i * axis_size
        tag = raw[base:base + 4].decode("latin-1")
        default = struct.unpack_from(">i", raw, base + 8)[0] / 65536.0
        out[tag] = default
    return out


def check_index(index_path):
    """Re-derive the cross-font studies: optical sizes, and variable font instances.

    The optical study is fully re-derived. Variable instances away from the default location are
    NOT: interpolating gvar deltas is not implemented here, and reporting them as checked would
    be a lie. They are counted and named as unchecked instead.
    """
    with open(index_path, encoding="utf-8") as fh:
        index = json.load(fh)
    problems, unchecked, checks = [], [], 0

    for member in index["optical"]["members"]:
        path = _locate(member)
        sfnt = Sfnt(path)
        cmap = cmap_codepoints(sfnt)
        for measure, char, edge in (("x_height", "x", 3), ("cap_height", "H", 3)):
            box = glyph_bbox(sfnt, cmap[ord(char)])
            mine = int(round(box[edge]))
            checks += 1
            if mine != member[measure]:
                problems.append(f"{member['file_name']} {measure}: generator says "
                                f"{member[measure]}, the outline gives {mine}")
        checks += 1
        mine_adv = advance_width(sfnt, cmap[ord("n")])
        if mine_adv != member["advance_n"]:
            problems.append(f"{member['file_name']} advance of 'n': generator says "
                            f"{member['advance_n']}, hmtx says {mine_adv}")
        raw_size = size_feature_raw(sfnt)
        checks += 1
        mine_design = None if raw_size is None else raw_size["design_size"]
        if mine_design != member["design_size_decipoints"]:
            problems.append(f"{member['file_name']} design size: generator says "
                            f"{member['design_size_decipoints']} decipoints, the bytes say "
                            f"{mine_design}")
        checks += 1
        expected_points = None if mine_design is None else mine_design / 10.0
        if expected_points != member["design_size"]:
            problems.append(f"{member['file_name']} design size in points: generator says "
                            f"{member['design_size']}, the bytes give {expected_points}")
        # The ratios the page draws a conclusion from, recomputed rather than trusted.
        checks += 1
        # The one genuinely floating-point comparison here, so the tolerance is RELATIVE to the
        # value rather than a fixed number of units.
        ratio = round(member["x_height"] / member["cap_height"], 4)
        if not _close(ratio, member["x_over_cap"]):
            problems.append(f"{member['file_name']} x/cap: generator says "
                            f"{member['x_over_cap']}, the parts give {ratio}")

    for inst in index["variable"]:
        path = _locate(inst)
        sfnt = Sfnt(path)
        defaults = fvar_defaults(sfnt)
        if defaults is None:
            problems.append(f"{inst['file_name']}: the generator reports variable instances for "
                            f"a font with no fvar table")
            continue
        at_default = all(defaults.get(k) == v for k, v in inst["location"].items())
        checks += 1
        if at_default != inst["is_default_instance"]:
            problems.append(f"{inst['suffix']}: generator says default={inst['is_default_instance']}, "
                            f"fvar defaults are {defaults}")
        if not at_default:
            unchecked.append(f"{inst['slug']} instance {inst['suffix']} at {inst['location']}: "
                             f"this checker does not interpolate gvar deltas, so its x-height "
                             f"and cap height are NOT independently confirmed")
            continue
        cmap = cmap_codepoints(sfnt)
        for measure, char, edge in (("x_height", "x", 3), ("cap_height", "H", 3)):
            box = glyph_bbox(sfnt, cmap[ord(char)])
            mine = int(round(box[edge]))
            checks += 1
            if mine != inst[measure]:
                problems.append(f"{inst['suffix']} {measure}: generator says {inst[measure]}, "
                                f"the default-instance outline gives {mine}")
    return {"checks": checks, "problems": problems, "unchecked": unchecked}


def main(argv):
    if not argv:
        print("usage: check_font_facts.py out/*.json", file=sys.stderr)
        return 2
    total_checks, failed = 0, 0
    index_paths = [p for p in argv if os.path.basename(p) == "_index.json"]
    for facts_path in sorted(argv):
        if os.path.basename(facts_path).startswith("_"):
            continue
        result = check_one(facts_path)
        total_checks += result["checks"]
        if result["problems"]:
            failed += 1
            print(f"FAIL  {result['font']}  ({result['checks']} facts re-derived)")
            for problem in result["problems"]:
                print(f"        {problem}")
        else:
            print(f"ok    {result['font']}  {result['checks']} facts re-derived from the "
                  f"font's bytes, all matching")
        for note in result["unsupported"]:
            print(f"        COULD NOT CHECK  {note}")
            failed += 1
    font_count = len([a for a in argv if not os.path.basename(a).startswith("_")])

    for index_path in index_paths:
        study = check_index(index_path)
        total_checks += study["checks"]
        if study["problems"]:
            failed += 1
            print(f"FAIL  cross-font studies  ({study['checks']} facts re-derived)")
            for problem in study["problems"]:
                print(f"        {problem}")
        else:
            print(f"ok    cross-font studies  {study['checks']} facts re-derived from the "
                  f"fonts' bytes, all matching")
        for note in study["unchecked"]:
            print(f"        NOT CHECKED  {note}")

    print(f"{total_checks} facts re-derived independently across {font_count} fonts"
          f"{' plus the cross-font studies' if index_paths else ''}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
