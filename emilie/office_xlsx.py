"""Excel (.xlsx) tools, standard library only: xlsx_read, xlsx_write. Also pptx_read for PowerPoint.

xlsx_write changes only the cells you name; every other part of the workbook (styles, charts, other sheets, defined
names, macros-free extras) is copied byte for byte. Formulas are stored without a cached result, and the workbook is
flagged to recalculate when Excel opens it. Not supported: creating charts, pivot tables, conditional formats, merged
cells or styles; adding a sheet to an EXISTING workbook (a NEW workbook can have several sheets).
"""
from __future__ import annotations

import datetime as dt
import io
import os
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from .office_docx import parse_xml, serialize

MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
RELNS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
X = "{%s}" % MAIN
R = "{%s}" % RELNS
MAX_BYTES = 60 * 1024 * 1024
BUILTIN_DATE_FMTS = {14, 15, 16, 17, 18, 19, 20, 21, 22, 45, 46, 47}


class XlsxError(Exception):
    pass


def col_letters(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def col_number(letters: str) -> int:
    n = 0
    for ch in letters.upper():
        n = n * 26 + ord(ch) - 64
    return n


def split_ref(ref: str) -> tuple[int, int]:
    m = re.fullmatch(r"\$?([A-Za-z]{1,3})\$?(\d{1,7})", ref.strip())
    if not m:
        raise XlsxError(f"'{ref}' is not a cell reference like B7")
    return int(m.group(2)), col_number(m.group(1))


class Book:
    def __init__(self, path: Path):
        if path.suffix.lower() not in (".xlsx", ".xlsm"):
            raise XlsxError(f"{path.name} is not an .xlsx file (old .xls files must be saved as .xlsx first)")
        if not path.is_file():
            raise XlsxError(f"{path} not found")
        if path.stat().st_size > MAX_BYTES:
            raise XlsxError("file is larger than 60 MB")
        self.path = path
        try:
            with zipfile.ZipFile(path) as z:
                self.order = [i.filename for i in z.infolist()]
                self.parts = {n: z.read(n) for n in self.order}
        except zipfile.BadZipFile:
            raise XlsxError("not a valid .xlsx (damaged zip, or password-protected)")
        if "xl/workbook.xml" not in self.parts:
            raise XlsxError("not an Excel workbook: xl/workbook.xml is missing")
        self.wb = parse_xml(self.parts["xl/workbook.xml"])
        rels = parse_xml(self.parts["xl/_rels/workbook.xml.rels"]) if "xl/_rels/workbook.xml.rels" in self.parts else None
        rmap = {r.get("Id"): r.get("Target") for r in rels} if rels is not None else {}
        self.sheets: list[tuple[str, str]] = []              # (name, part path)
        for s in self.wb.iter(X + "sheet"):
            tgt = rmap.get(s.get(R + "id"), "")
            tgt = tgt.lstrip("/") if tgt.startswith("/") else "xl/" + tgt
            self.sheets.append((s.get("name", ""), tgt))
        self._shared: list[str] | None = None
        self._datefmt: set[int] | None = None

    @property
    def shared(self) -> list[str]:
        if self._shared is None:
            self._shared = []
            data = self.parts.get("xl/sharedStrings.xml")
            if data:
                for si in parse_xml(data).iter(X + "si"):
                    self._shared.append("".join(t.text or "" for t in si.iter(X + "t")))
        return self._shared

    @property
    def date_styles(self) -> set[int]:
        """cellXfs indexes whose number format is a date/time."""
        if self._datefmt is None:
            self._datefmt = set()
            data = self.parts.get("xl/styles.xml")
            if data:
                root = parse_xml(data)
                custom = {}
                for nf in root.iter(X + "numFmt"):
                    code = re.sub(r'"[^"]*"|\[[^\]]*\]|\\.', "", nf.get("formatCode", "")).lower()
                    if re.search(r"[ymdhs]", code) and not re.search(r"0|#", code.replace("mm", "")):
                        custom[int(nf.get("numFmtId"))] = True
                xfs = root.find(X + "cellXfs")
                if xfs is not None:
                    for i, xf in enumerate(xfs.findall(X + "xf")):
                        fid = int(xf.get("numFmtId", "0"))
                        if fid in BUILTIN_DATE_FMTS or custom.get(fid):
                            self._datefmt.add(i)
        return self._datefmt

    def sheet_part(self, name: str) -> str:
        if not name:
            if not self.sheets:
                raise XlsxError("the workbook has no sheets")
            return self.sheets[0][1]
        for n, part in self.sheets:
            if n == name:
                return part
        for n, part in self.sheets:
            if n.lower() == name.lower():
                return part
        raise XlsxError(f"sheet '{name}' not found. Sheets: {', '.join(n for n, _ in self.sheets)}")

    def cell_value(self, c: ET.Element):
        t = c.get("t", "n")
        v = c.find(X + "v")
        f = c.find(X + "f")
        if t == "inlineStr":
            val = "".join(x.text or "" for x in c.iter(X + "t"))
        elif v is None or v.text is None:
            val = None
        elif t == "s":
            idx = int(v.text)
            val = self.shared[idx] if idx < len(self.shared) else f"#sst{idx}"
        elif t == "b":
            val = v.text == "1"
        elif t in ("str", "e"):
            val = v.text
        else:
            try:
                num = float(v.text)
            except ValueError:
                num = None
            if num is None:
                val = v.text
            elif int(c.get("s", "0")) in self.date_styles and 0 < num < 2958466:
                base = dt.datetime(1899, 12, 30) + dt.timedelta(days=num)
                val = base.strftime("%Y-%m-%d") if num == int(num) else base.strftime("%Y-%m-%d %H:%M:%S")
            else:
                val = int(num) if num == int(num) and abs(num) < 1e15 else num
        return val, (f.text if f is not None and f.text else ("(shared formula)" if f is not None else None))

    def save(self, update_dim: dict[str, ET.Element] | None = None) -> None:
        target = self.path
        tmp = target.with_name(target.name + ".emilie-tmp")
        names = list(self.order) + [n for n in self.parts if n not in self.order]
        try:
            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
                for n in names:
                    if n in self.parts:
                        z.writestr(n, self.parts[n])
            os.replace(tmp, target)
        except PermissionError:
            tmp.unlink(missing_ok=True)
            raise XlsxError(f"cannot write {target.name}: it is probably open in Excel. Close it and try again.")


# ------------------------------------------------------------------ read
def xlsx_read(path: str, sheet: str = "", range: str = "", max_rows: int = 100) -> str:
    from . import tools
    try:
        bk = Book(Path(path).expanduser())
        part = bk.sheet_part(sheet)
        if part not in bk.parts:
            raise XlsxError(f"the sheet data ({part}) is missing from the file")
        root = parse_xml(bk.parts[part])
        lo = hi = None
        if range:
            a, _, b = range.partition(":")
            lo = split_ref(a)
            hi = split_ref(b or a)
        rows: dict[int, dict[int, tuple]] = {}
        formulas = []
        for c in root.iter(X + "c"):
            ref = c.get("r", "")
            try:
                r, col = split_ref(ref)
            except XlsxError:
                continue
            if lo and not (lo[0] <= r <= hi[0] and lo[1] <= col <= hi[1]):
                continue
            val, form = bk.cell_value(c)
            if val is None and form is None:
                continue
            rows.setdefault(r, {})[col] = (val, form)
            if form:
                formulas.append(f"{ref}: ={form.lstrip('=')}")
        names = ", ".join(f"{n}" for n, _ in bk.sheets)
        cur = sheet or bk.sheets[0][0]
        if not rows:
            return f"{Path(path).name}\nsheets: {names}\n\nsheet '{cur}' has no values" + (f" in {range}" if range else "") + "."
        maxcol = min(max(max(r) for r in rows.values()), 40)
        mincol = min(min(r) for r in rows.values())
        lines = [f"{Path(path).name}  |  sheets: {names}", f"showing sheet '{cur}'" + (f", range {range}" if range else "")
                 + f"  ({len(rows)} non-empty rows)", ""]
        lines.append("      " + " | ".join(col_letters(c) for c in range_(mincol, maxcol + 1)))
        shown = 0
        for r in sorted(rows):
            if shown >= max(1, int(max_rows or 100)):
                lines.append(f"... more rows; use range='A{r}:{col_letters(maxcol)}{r + 99}' to continue")
                break
            cells = []
            for c in range_(mincol, maxcol + 1):
                v = rows[r].get(c, (None, None))[0]
                cells.append("" if v is None else (str(v).replace("\n", "\\n")[:60]))
            lines.append(f"{r:>5} " + " | ".join(cells))
            shown += 1
        if formulas:
            lines.append("")
            lines.append("formulas (the value shown above is Excel's last calculated result):")
            lines += ["  " + f for f in formulas[:40]] + ([f"  ... {len(formulas) - 40} more"] if len(formulas) > 40 else [])
        return tools._clip("\n".join(lines))
    except XlsxError as e:
        return f"ERROR: {e}"
    except (OSError, ET.ParseError) as e:
        return f"ERROR: {e}"


range_ = range      # the parameter named `range` shadows the builtin inside xlsx_read


# ------------------------------------------------------------------ write
def _set_cell(root: ET.Element, ref: str, value) -> None:
    r, c = split_ref(ref)
    data = root.find(X + "sheetData")
    if data is None:
        raise XlsxError("the sheet has no sheetData")
    row = next((x for x in data.findall(X + "row") if int(x.get("r", "0")) == r), None)
    if row is None:
        row = ET.Element(X + "row")
        row.set("r", str(r))
        pos = 0
        for k, x in enumerate(data.findall(X + "row")):
            if int(x.get("r", "0")) < r:
                pos = k + 1
        data.insert(pos, row)
    row.attrib.pop("spans", None)
    cell = next((x for x in row.findall(X + "c") if split_ref(x.get("r", "A1"))[1] == c), None)
    if cell is None:
        cell = ET.Element(X + "c")
        cell.set("r", f"{col_letters(c)}{r}")
        pos = 0
        for k, x in enumerate(row.findall(X + "c")):
            if split_ref(x.get("r", "A1"))[1] < c:
                pos = k + 1
        row.insert(pos, cell)
    style = cell.get("s")
    for ch in list(cell):
        cell.remove(ch)
    cell.attrib.pop("t", None)
    if value is None or value == "":
        return                                    # an empty styled cell stays as a blank
    if isinstance(value, bool):
        cell.set("t", "b")
        ET.SubElement(cell, X + "v").text = "1" if value else "0"
    elif isinstance(value, (int, float)):
        ET.SubElement(cell, X + "v").text = repr(value) if isinstance(value, float) else str(value)
    elif isinstance(value, str) and value.startswith("="):
        ET.SubElement(cell, X + "f").text = value[1:]
    else:
        cell.set("t", "inlineStr")
        is_ = ET.SubElement(cell, X + "is")
        t = ET.SubElement(is_, X + "t")
        t.text = str(value)
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    if style is not None:
        cell.set("s", style)


def _fix_dimension(root: ET.Element) -> None:
    refs = [split_ref(c.get("r")) for c in root.iter(X + "c") if c.get("r")]
    if not refs:
        return
    r0, r1 = min(r for r, _ in refs), max(r for r, _ in refs)
    c0, c1 = min(c for _, c in refs), max(c for _, c in refs)
    dim = root.find(X + "dimension")
    text = f"{col_letters(c0)}{r0}:{col_letters(c1)}{r1}"
    if dim is not None:
        dim.set("ref", text)


def _new_book(path: Path, sheets: dict[str, dict]) -> None:
    names = list(sheets) or ["Sheet1"]
    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
          '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
          + "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                    for i in range_(1, len(names) + 1)) + '</Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            f'<Relationships xmlns="{PKG_REL}"><Relationship Id="rId1" Type="{RELNS}/officeDocument" Target="xl/workbook.xml"/></Relationships>')
    wb = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
          f'<workbook xmlns="{MAIN}" xmlns:r="{RELNS}"><sheets>'
          + "".join(f'<sheet name="{_x(n)}" sheetId="{i}" r:id="rId{i}"/>' for i, n in enumerate(names, 1))
          + '</sheets><calcPr calcId="191029" fullCalcOnLoad="1"/></workbook>')
    wbrels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
              f'<Relationships xmlns="{PKG_REL}">'
              + "".join(f'<Relationship Id="rId{i}" Type="{RELNS}/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range_(1, len(names) + 1))
              + f'<Relationship Id="rId{len(names) + 1}" Type="{RELNS}/styles" Target="styles.xml"/></Relationships>')
    styles = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
              f'<styleSheet xmlns="{MAIN}"><fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
              '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
              '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
              '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
              '<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>'
              '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".emilie-tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("_rels/.rels", rels)
        z.writestr("xl/workbook.xml", wb)
        z.writestr("xl/_rels/workbook.xml.rels", wbrels)
        z.writestr("xl/styles.xml", styles)
        for i, n in enumerate(names, 1):
            z.writestr(f"xl/worksheets/sheet{i}.xml",
                       f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<worksheet xmlns="{MAIN}"><dimension ref="A1"/><sheetData/></worksheet>')
    os.replace(tmp, path)


def _x(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def xlsx_write(path: str, cells: dict | None = None, sheet: str = "") -> str:
    """cells: {"A1": 5, "B2": "text", "C3": "=SUM(A1:B2)", "Data!D4": 1.5} - 'Sheet!' picks a sheet; others use `sheet` or the first."""
    p = Path(path).expanduser()
    if not isinstance(cells, dict) or not cells:
        return "ERROR: give cells as an object like {\"A1\": \"Name\", \"B1\": 42, \"C1\": \"=A1&B1\"}"
    try:
        grouped: dict[str, dict[str, object]] = {}
        default = sheet or ""
        for ref, val in cells.items():
            sh, _, cr = str(ref).rpartition("!")
            split_ref(cr)                                       # validates
            grouped.setdefault(sh.strip("'") or default, {})[cr] = val
        created = False
        if not p.exists():
            if p.suffix.lower() != ".xlsx":
                return "ERROR: the file name must end with .xlsx"
            _new_book(p, {(k or "Sheet1"): {} for k in grouped} or {"Sheet1": {}})
            created = True
            grouped = {(k or "Sheet1"): v for k, v in grouped.items()}
        bk = Book(p)
        total = 0
        for sh, items in grouped.items():
            part = bk.sheet_part(sh)
            root = parse_xml(bk.parts[part])
            raw = bk.parts[part]
            for ref, val in items.items():
                _set_cell(root, ref, val)
                total += 1
            _fix_dimension(root)
            bk.parts[part] = serialize(root, raw)
        if any(isinstance(v, str) and v.startswith("=") for items in grouped.values() for v in items.values()):
            raw = bk.parts["xl/workbook.xml"]
            wb = bk.wb
            cp = wb.find(X + "calcPr")
            if cp is None:
                cp = ET.SubElement(wb, X + "calcPr")
            cp.set("fullCalcOnLoad", "1")
            bk.parts["xl/workbook.xml"] = serialize(wb, raw)
        bk.parts.pop("xl/calcChain.xml", None)                   # stale chain would make Excel repair the file
        if "xl/calcChain.xml" in bk.order:
            bk.order.remove("xl/calcChain.xml")
            ct = bk.parts["[Content_Types].xml"].decode("utf-8")
            ct = re.sub(r'<Override[^>]*calcChain[^>]*/>', "", ct)
            bk.parts["[Content_Types].xml"] = ct.encode("utf-8")
            rn = "xl/_rels/workbook.xml.rels"
            if rn in bk.parts:
                bk.parts[rn] = re.sub(r'<Relationship[^>]*calcChain[^>]*/>', "", bk.parts[rn].decode("utf-8")).encode("utf-8")
        bk.save()
        return (f"{'created' if created else 'updated'} {p.name}: set {total} cell(s) in {', '.join(k or bk.sheets[0][0] for k in grouped)}. "
                f"Formulas have no stored result until Excel opens the file (it recalculates automatically); read it back with xlsx_read.")
    except XlsxError as e:
        return f"ERROR: {e}"
    except (OSError, ET.ParseError) as e:
        return f"ERROR: {e}"


# ------------------------------------------------------------------ pptx (read)
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"


def pptx_read(path: str, slide: int = 0) -> str:
    from . import tools
    p = Path(path).expanduser()
    try:
        if p.suffix.lower() != ".pptx":
            return f"ERROR: {p.name} is not a .pptx file"
        if not p.is_file():
            return f"ERROR: {p} not found"
        with zipfile.ZipFile(p) as z:
            parts = {n: z.read(n) for n in z.namelist() if n.endswith(".xml") or n.endswith(".rels")}
        pres = parse_xml(parts["ppt/presentation.xml"])
        rels = {r.get("Id"): r.get("Target") for r in parse_xml(parts["ppt/_rels/presentation.xml.rels"])}
        order = []
        for sid in pres.iter(P + "sldId"):
            tgt = rels.get(sid.get(R + "id"), "")
            order.append(("ppt/" + tgt.lstrip("/")) if not tgt.startswith("/") else tgt.lstrip("/"))
        out = [f"{p.name}: {len(order)} slides"]
        for n, part in enumerate(order, 1):
            if slide and n != slide:
                continue
            root = parse_xml(parts[part])
            out.append(f"\n--- slide {n} ---")
            for sp in root.iter(P + "sp"):
                ph = sp.find(f"{P}nvSpPr/{P}nvPr/{P}ph")
                kind = ph.get("type", "body") if ph is not None else ""
                paras = ["".join(t.text or "" for t in para.iter(A + "t")) for para in sp.iter(A + "p")]
                text = "\n".join(x for x in paras if x.strip())
                if text:
                    out.append((f"[{kind}] " if kind in ("title", "ctrTitle", "subTitle") else "") + text)
            for tbl in root.iter(A + "tbl"):
                for r in tbl.iter(A + "tr"):
                    out.append("  | " + " | ".join("".join(t.text or "" for t in c.iter(A + "t")) for c in r.iter(A + "tc")))
            pics = len(list(root.iter(P + "pic")))
            if pics:
                out.append(f"({pics} picture(s))")
            relp = part.replace("slides/", "slides/_rels/") + ".rels"
            note = None
            if relp in parts:
                for r in parse_xml(parts[relp]):
                    if r.get("Type", "").endswith("/notesSlide"):
                        note = "ppt/" + r.get("Target", "").replace("../", "")
            if note and note in parts:
                nt = "\n".join("".join(t.text or "" for t in para.iter(A + "t")) for para in parse_xml(parts[note]).iter(A + "p"))
                nt = "\n".join(l for l in nt.splitlines() if l.strip() and not l.strip().isdigit())
                if nt.strip():
                    out.append("notes: " + nt.strip()[:600])
        return tools._clip("\n".join(out))
    except (KeyError, zipfile.BadZipFile, ET.ParseError, OSError) as e:
        return f"ERROR: could not read the presentation: {type(e).__name__}: {e}"


# ------------------------------------------------------------------ registry
def specs(_schema, _s, _i):
    return {
        "xlsx_read": (xlsx_read, _schema(
            "xlsx_read",
            "Read an Excel workbook (.xlsx): lists the sheets and prints a sheet as a grid (rows with column letters). Dates are "
            "shown as dates, formulas are listed with their last calculated value. sheet picks a sheet (default the first); "
            "range like 'A1:F40' limits it; max_rows (default 100).",
            {"path": _s, "sheet": _s, "range": _s, "max_rows": _i}, ["path"]), "file", False),
        "xlsx_write": (xlsx_write, _schema(
            "xlsx_write",
            "Set cells in an Excel workbook (.xlsx), creating the file if it does not exist (then 'Sheet!A1' keys create those "
            "sheets). cells = {\"A1\": \"text\", \"B1\": 42, \"C1\": true, \"D1\": \"=SUM(B1:B9)\", \"Data!A2\": 1.5}; a string "
            "starting with '=' is a formula; null/\"\" empties a cell. Only the named cells change; styles, other sheets and charts "
            "stay. Cannot add sheets to an existing workbook, draw charts, or style cells.",
            {"path": _s, "cells": {"type": "object"}, "sheet": _s}, ["path", "cells"]), "file", True),
        "pptx_read": (pptx_read, _schema(
            "pptx_read",
            "Read a PowerPoint presentation (.pptx): per slide the titles, text, tables, picture count and speaker notes. "
            "slide=N reads one slide. Read only.",
            {"path": _s, "slide": _i}, ["path"]), "file", False),
    }
