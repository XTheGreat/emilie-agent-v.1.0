"""Word (.docx) tools, standard library only: docx_read, docx_edit, docx_create.

A .docx is a zip of XML parts. Editing rewrites only word/document.xml (plus the small parts an inserted picture needs);
every other part (styles, headers, footers, comments, theme, macros, custom XML) is copied byte for byte, so the
document keeps its look. Not supported: tracked changes (existing ones are left alone, new edits are plain), editing
inside headers/footers/text boxes/footnotes, content controls' data binding, layout rendering (no page numbers).
"""
from __future__ import annotations

import copy
import io
import os
import re
import struct
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

WNS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
RNS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
W = "{%s}" % WNS
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
MAX_BYTES = 60 * 1024 * 1024
IMG_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".bmp": "image/bmp"}


for _p, _u in (("wp", "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"),
               ("a", "http://schemas.openxmlformats.org/drawingml/2006/main"),
               ("pic", "http://schemas.openxmlformats.org/drawingml/2006/picture"), ("r", RNS), ("w", WNS)):
    ET.register_namespace(_p, _u)


class DocxError(Exception):
    pass


# ------------------------------------------------------------------ package
class Package:
    def __init__(self, path: Path):
        if path.suffix.lower() != ".docx":
            raise DocxError(f"{path.name} is not a .docx file (an old .doc must be saved as .docx first)")
        if not path.is_file():
            raise DocxError(f"{path} not found")
        if path.stat().st_size > MAX_BYTES:
            raise DocxError("file is larger than 60 MB")
        self.path = path
        try:
            with zipfile.ZipFile(path) as z:
                self.order = [i.filename for i in z.infolist()]
                self.parts = {n: z.read(n) for n in self.order}
        except zipfile.BadZipFile:
            raise DocxError("not a valid .docx (the zip is damaged or the file is password-protected)")
        if "word/document.xml" not in self.parts:
            raise DocxError("not a Word document: word/document.xml is missing")
        self.raw_doc = self.parts["word/document.xml"]
        self.root = parse_xml(self.raw_doc)
        self.body = self.root.find(W + "body")
        if self.body is None:
            raise DocxError("the document has no body")

    def style_map(self) -> dict[str, tuple[str, str]]:
        """styleId -> (lowercase name, type)"""
        data = self.parts.get("word/styles.xml")
        out: dict[str, tuple[str, str]] = {}
        if not data:
            return out
        for s in parse_xml(data).iter(W + "style"):
            sid = s.get(W + "styleId")
            nm = s.find(W + "name")
            out[sid] = ((nm.get(W + "val") if nm is not None else sid).lower(), s.get(W + "type", ""))
        return out

    def resolve_style(self, wanted: str, kind: str = "paragraph") -> str:
        sm = self.style_map()
        w = re.sub(r"\s+", "", wanted).lower()
        for sid, (name, typ) in sm.items():
            if typ == kind and (sid.lower() == w or re.sub(r"\s+", "", name) == w):
                return sid
        avail = sorted({n for _, (n, t) in sm.items() if t == kind})[:25]
        raise DocxError(f"style '{wanted}' does not exist in this document. Available {kind} styles: {', '.join(avail) or '(none)'}")

    def save(self, path: Path | None = None) -> None:
        self.parts["word/document.xml"] = serialize(self.root, self.raw_doc)
        target = path or self.path
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
            raise DocxError(f"cannot write {target.name}: it is probably open in Word or another program. Close it and try again.")

    # rels / content types, used when a picture is added
    def add_image(self, img: Path) -> str:
        ext = img.suffix.lower()
        if ext not in IMG_TYPES:
            raise DocxError(f"image type {ext or '?'} is not supported (use png, jpg, gif or bmp)")
        n = 1
        while f"word/media/emilie{n}{ext}" in self.parts:
            n += 1
        name = f"word/media/emilie{n}{ext}"
        self.parts[name] = img.read_bytes()
        ct = self.parts["[Content_Types].xml"].decode("utf-8")
        if f'Extension="{ext[1:]}"' not in ct and f"Extension='{ext[1:]}'" not in ct:
            ct = ct.replace("<Default ", f'<Default Extension="{ext[1:]}" ContentType="{IMG_TYPES[ext]}"/><Default ', 1)
            self.parts["[Content_Types].xml"] = ct.encode("utf-8")
        rels_name = "word/_rels/document.xml.rels"
        rels = self.parts.get(rels_name, f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="{PKG_REL}"></Relationships>'.encode())
        text = rels.decode("utf-8")
        ids = [int(x) for x in re.findall(r'Id="rId(\d+)"', text)]
        rid = f"rId{max(ids, default=0) + 1}"
        text = text.replace("</Relationships>", f'<Relationship Id="{rid}" Type="{RNS}/image" Target="media/emilie{n}{ext}"/></Relationships>')
        self.parts[rels_name] = text.encode("utf-8")
        return rid


def parse_xml(data: bytes) -> ET.Element:
    for _, (prefix, uri) in ET.iterparse(io.BytesIO(data), events=("start-ns",)):
        try:
            ET.register_namespace(prefix, uri)
        except ValueError:
            pass
    return ET.fromstring(data)


def serialize(root: ET.Element, original: bytes) -> bytes:
    """ElementTree drops unused xmlns declarations that mc:Ignorable still refers to, which makes Word reject the file.
    Keep the ORIGINAL root start tag (all declarations and attributes) and only add prefixes that ET introduced."""
    text = ET.tostring(root, encoding="unicode")
    orig = original.decode("utf-8-sig")
    decl_m = re.match(r"\s*<\?xml[^>]*\?>\s*", orig)
    decl = decl_m.group(0) if decl_m else '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    old_tag = re.search(r"<(?![?!])[^>]*>", orig).group(0)
    new_tag = re.match(r"<[^>]*>", text).group(0)
    for pfx, uri in re.findall(r'xmlns:([\w.-]+)="([^"]*)"', new_tag):
        if not re.search(rf'xmlns:{re.escape(pfx)}=', old_tag):
            old_tag = old_tag[:-1] + f' xmlns:{pfx}="{uri}">'
    return (decl + old_tag + text[len(new_tag):]).encode("utf-8")


# ------------------------------------------------------------------ reading
def _flat_children(body: ET.Element):
    for ch in body:
        if ch.tag == W + "sdt":
            content = ch.find(W + "sdtContent")
            if content is not None:
                yield from _flat_children(content)
        elif ch.tag in (W + "p", W + "tbl"):
            yield ch


def p_text(p: ET.Element) -> str:
    out = []
    for e in p.iter():
        if e.tag == W + "t":
            out.append(e.text or "")
        elif e.tag == W + "tab":
            out.append("\t")
        elif e.tag == W + "br" and e.get(W + "type") == "page":
            out.append("[page break]")
        elif e.tag in (W + "br", W + "cr"):
            out.append("\n")
        elif e.tag == W + "noBreakHyphen":
            out.append("-")
    return "".join(out)


def p_style(p: ET.Element) -> str:
    st = p.find(f"{W}pPr/{W}pStyle")
    return st.get(W + "val", "") if st is not None else ""


def _is_list(p: ET.Element) -> bool:
    return p.find(f"{W}pPr/{W}numPr") is not None


def _cells(tr: ET.Element):
    return [tc for tc in tr.findall(W + "tc")]


def _cell_text(tc: ET.Element) -> str:
    return " / ".join(t for t in (p_text(p).strip() for p in tc.iter(W + "p")) if t)


def _num_formats(pkg: "Package") -> dict[tuple[str, str], str]:
    """(numId, ilvl) -> numFmt (decimal, bullet, lowerLetter ...) from numbering.xml."""
    data = pkg.parts.get("word/numbering.xml")
    out: dict[tuple[str, str], str] = {}
    if not data:
        return out
    root = parse_xml(data)
    abstract: dict[str, dict[str, str]] = {}
    for a in root.findall(W + "abstractNum"):
        lv = {}
        for l in a.findall(W + "lvl"):
            f = l.find(W + "numFmt")
            lv[l.get(W + "ilvl", "0")] = f.get(W + "val", "bullet") if f is not None else "bullet"
        abstract[a.get(W + "abstractNumId")] = lv
    for n in root.findall(W + "num"):
        ref = n.find(W + "abstractNumId")
        if ref is not None:
            for lvl, fmt in abstract.get(ref.get(W + "val"), {}).items():
                out[(n.get(W + "numId"), lvl)] = fmt
    return out


def _list_label(p: ET.Element, fmts: dict, counters: dict) -> str:
    npr = p.find(f"{W}pPr/{W}numPr")
    if npr is None:
        return ""
    nid = npr.find(W + "numId")
    lv = npr.find(W + "ilvl")
    numid = nid.get(W + "val", "0") if nid is not None else "0"
    ilvl = lv.get(W + "val", "0") if lv is not None else "0"
    fmt = fmts.get((numid, ilvl), "bullet")
    pad = "  " * int(ilvl) if ilvl.isdigit() else ""
    if fmt in ("decimal", "lowerLetter", "upperLetter", "lowerRoman", "upperRoman"):
        k = counters[(numid, ilvl)] = counters.get((numid, ilvl), 0) + 1
        for key in [x for x in counters if x[0] == numid and x[1] > ilvl]:       # deeper levels restart
            del counters[key]
        if fmt == "lowerLetter":
            return f"{pad}{chr(96 + (k - 1) % 26 + 1)}. "
        if fmt == "upperLetter":
            return f"{pad}{chr(64 + (k - 1) % 26 + 1)}. "
        return f"{pad}{k}. "
    return f"{pad}• "


def docx_read(path: str, offset: int = 1, limit: int = 0) -> str:
    from . import tools
    try:
        pkg = Package(Path(path).expanduser())
    except DocxError as e:
        return f"ERROR: {e}"
    names = pkg.style_map()
    fmts, counters = _num_formats(pkg), {}
    lines, pi, ti = [], 0, 0
    flat = list(_flat_children(pkg.body))
    for el in flat:
        if el.tag == W + "p":
            pi += 1
            st = p_style(el)
            label = names.get(st, (st, ""))[0] if st else ""
            mark = _list_label(el, fmts, counters)
            txt = p_text(el)
            has_img = any(True for _ in el.iter(W + "drawing")) or any(True for _ in el.iter(W + "pict"))
            lines.append((pi, f"[{pi}]" + (f" ({label})" if label and label != "normal" else "") + f" {mark}{txt}" + (" [picture]" if has_img else "")))
        else:
            ti += 1
            rows = el.findall(W + "tr")
            ncols = max((len(_cells(r)) for r in rows), default=0)
            block = [f"[T{ti}] table {len(rows)} rows x {ncols} columns"]
            for r_i, r in enumerate(rows[:60], 1):
                block.append(f"    R{r_i}: " + " | ".join(_cell_text(c) for c in _cells(r)))
            if len(rows) > 60:
                block.append(f"    ... {len(rows) - 60} more rows")
            lines.append((pi, "\n".join(block)))
    start = max(1, int(offset or 1))
    cap = int(limit or 400)
    shown = [txt for n, txt in lines if n >= start][:cap] if lines else []
    extras = []
    for n in sorted(k for k in pkg.parts if re.match(r"word/(header|footer)\d*\.xml$", k)):
        t = " ".join(p_text(p).strip() for p in parse_xml(pkg.parts[n]).iter(W + "p")).strip()
        if t:
            extras.append(f"{n.split('/')[-1]}: {t[:120]}")
    for kind, nm in (("comments", "word/comments.xml"), ("footnotes", "word/footnotes.xml")):
        if nm in pkg.parts:
            c = len(re.findall(rb"<w:(comment|footnote) ", pkg.parts[nm]))
            if c:
                extras.append(f"{c} {kind} (not shown)")
    if pkg.parts.get("word/document.xml", b"").find(b"<w:ins ") >= 0 or pkg.raw_doc.find(b"<w:del ") >= 0:
        extras.append("the document contains tracked changes (insertions/deletions are shown as plain text; they are left as they are)")
    head = f"{Path(path).name}: {pi} paragraphs, {ti} tables"
    body = "\n".join(shown) or "(empty document)"
    more = ""
    if pi and start + cap <= pi + ti and len(shown) >= cap:
        more = f"\n...[more content; pass offset={start + cap} for the rest]"
    tail = ("\n\n" + "\n".join(extras)) if extras else ""
    return tools._clip(head + "\n\n" + body + more + tail)


# ------------------------------------------------------------------ building blocks
def _el(tag: str, **attrs) -> ET.Element:
    e = ET.Element(W + tag)
    for k, v in attrs.items():
        e.set(W + k, str(v))
    return e


def _rpr(base: ET.Element | None, bold=False, italic=False, code=False) -> ET.Element | None:
    rpr = copy.deepcopy(base) if base is not None else None
    if not (bold or italic or code):
        return rpr
    if rpr is None:
        rpr = ET.Element(W + "rPr")
    def put(tag, el):
        if rpr.find(W + tag) is None:
            pos = 0
            order = ["rStyle", "rFonts", "b", "bCs", "i", "iCs"]
            for k, ch in enumerate(list(rpr)):
                nm = ch.tag.replace(W, "")
                if nm in order and order.index(nm) < order.index(tag):
                    pos = k + 1
            rpr.insert(pos, el)
    if code:
        put("rFonts", _el("rFonts", ascii="Consolas", hAnsi="Consolas", cs="Consolas"))
    if bold:
        put("b", _el("b"))
    if italic:
        put("i", _el("i"))
    return rpr


def _run(text: str, rpr: ET.Element | None) -> list[ET.Element]:
    out = []
    parts = text.split("\n")
    r = ET.Element(W + "r")
    if rpr is not None and len(rpr):
        r.append(copy.deepcopy(rpr))
    for k, part in enumerate(parts):
        if k:
            r.append(_el("br"))
        if part:
            t = ET.SubElement(r, W + "t")
            t.text = part
            t.set(XML_SPACE, "preserve")
    out.append(r)
    return out


INLINE = re.compile(r"(\*\*[^*\n]+?\*\*|\*[^*\s][^*\n]*?\*|`[^`\n]+`)")


def _runs_from_markup(text: str, base: ET.Element | None = None, markup: bool = True) -> list[ET.Element]:
    if not markup:
        return _run(text, base)
    out: list[ET.Element] = []
    for piece in INLINE.split(text):
        if not piece:
            continue
        if piece.startswith("**") and piece.endswith("**") and len(piece) > 4:
            out += _run(piece[2:-2], _rpr(base, bold=True))
        elif piece.startswith("`") and piece.endswith("`") and len(piece) > 2:
            out += _run(piece[1:-1], _rpr(base, code=True))
        elif piece.startswith("*") and piece.endswith("*") and len(piece) > 2:
            out += _run(piece[1:-1], _rpr(base, italic=True))
        else:
            out += _run(piece, base)
    return out


def _paragraph(text: str, style_id: str = "", base: ET.Element | None = None, markup: bool = True,
               numid: int = 0, ilvl: int = 0, align: str = "") -> ET.Element:
    p = ET.Element(W + "p")
    if style_id or numid or align:
        ppr = ET.SubElement(p, W + "pPr")
        if style_id:
            ppr.append(_el("pStyle", val=style_id))
        if numid:
            npr = ET.SubElement(ppr, W + "numPr")
            npr.append(_el("ilvl", val=ilvl))
            npr.append(_el("numId", val=numid))
        if align:
            ppr.append(_el("jc", val=align))
    for r in _runs_from_markup(text, base, markup):
        p.append(r)
    return p


def _table(rows: list[list[str]], header: bool, style_id: str = "") -> ET.Element:
    ncols = max(len(r) for r in rows)
    tbl = ET.Element(W + "tbl")
    pr = ET.SubElement(tbl, W + "tblPr")
    if style_id:
        pr.append(_el("tblStyle", val=style_id))
    pr.append(_el("tblW", w=5000, type="pct"))
    if not style_id:
        b = ET.SubElement(pr, W + "tblBorders")
        for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
            b.append(_el(side, val="single", sz=4, space=0, color="808080"))
    grid = ET.SubElement(tbl, W + "tblGrid")
    for _ in range(ncols):
        grid.append(_el("gridCol", w=max(600, 9000 // ncols)))
    for ri, row in enumerate(rows):
        tr = ET.SubElement(tbl, W + "tr")
        if header and ri == 0:
            trp = ET.SubElement(tr, W + "trPr")
            trp.append(_el("tblHeader"))
        for ci in range(ncols):
            tc = ET.SubElement(tr, W + "tc")
            tcp = ET.SubElement(tc, W + "tcPr")
            tcp.append(_el("tcW", w=max(600, 9000 // ncols), type="dxa"))
            if header and ri == 0:
                tcp.append(_el("shd", val="clear", color="auto", fill="E7E6E6"))
            txt = str(row[ci]) if ci < len(row) else ""
            tc.append(_paragraph(txt, "", _rpr(None, bold=True) if header and ri == 0 else None, markup=False))
    return tbl


def _png_size(data: bytes) -> tuple[int, int] | None:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", data[16:24])
    return None


def _img_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    sz = _png_size(data)
    if sz:
        return sz
    try:
        from PIL import Image
        with Image.open(path) as im:
            return im.size
    except Exception:
        return (800, 600)


def _drawing_paragraph(rid: str, img: Path, width_cm: float, idn: int, alt: str, align: str = "center") -> ET.Element:
    w_px, h_px = _img_size(img)
    cx = int(width_cm * 360000)
    cy = int(cx * h_px / max(w_px, 1))
    xml = (f'<w:r xmlns:w="{WNS}" xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
           f'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
           f'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture" xmlns:r="{RNS}"><w:drawing>'
           f'<wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="{cx}" cy="{cy}"/>'
           f'<wp:docPr id="{idn}" name="Picture {idn}" descr="{_esc(alt)}"/>'
           f'<wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/></wp:cNvGraphicFramePr>'
           f'<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:pic>'
           f'<pic:nvPicPr><pic:cNvPr id="{idn}" name="{_esc(img.name)}"/><pic:cNvPicPr/></pic:nvPicPr>'
           f'<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
           f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
           f'</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r>')
    p = ET.Element(W + "p")
    ppr = ET.SubElement(p, W + "pPr")
    ppr.append(_el("jc", val=align))
    p.append(ET.fromstring(xml))
    return p


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


# ------------------------------------------------------------------ editing
def _top_paragraphs(body: ET.Element) -> list[ET.Element]:
    return [c for c in _flat_children(body) if c.tag == W + "p"]


def _tables(body: ET.Element) -> list[ET.Element]:
    return [c for c in _flat_children(body) if c.tag == W + "tbl"]


def _body_insert(body: ET.Element, anchor: ET.Element | None, new: list[ET.Element], at_start=False) -> None:
    """Insert after anchor (a direct or nested-in-sdt child); at the very start, or before the final sectPr."""
    if at_start:
        pos = 0
    elif anchor is None:
        pos = len(body)
        if len(body) and body[-1].tag == W + "sectPr":
            pos -= 1
    else:
        holder, par = anchor, body
        if anchor not in list(body):                       # inside a content control: place after the whole control
            for sdt in body.findall(W + "sdt"):
                if anchor in list(sdt.iter()):
                    holder = sdt
                    break
        pos = list(par).index(holder) + 1
    for k, e in enumerate(new):
        body.insert(pos + k, e)


def _ensure_para_after_table(body: ET.Element) -> None:
    kids = [c for c in body if c.tag != W + "sectPr"]
    if kids and kids[-1].tag == W + "tbl":
        _body_insert(body, None, [ET.Element(W + "p")])


def _replace_in_paragraph(p: ET.Element, find: str, repl: str, case: bool) -> int:
    """Replace across run boundaries; the replacement takes the formatting of the first run the match touches."""
    ts = [t for t in p.iter(W + "t")]
    if not ts:
        return 0
    full = "".join(t.text or "" for t in ts)
    hay, needle = (full, find) if case else (full.lower(), find.lower())
    if needle not in hay:
        return 0
    bounds, pos = [], 0
    for t in ts:
        n = len(t.text or "")
        bounds.append((pos, pos + n))
        pos += n
    count, start = 0, 0
    spans = []
    while True:
        i = hay.find(needle, start)
        if i < 0:
            break
        spans.append((i, i + len(needle)))
        start = i + len(needle)
    for a, b in reversed(spans):                              # from the end so offsets stay valid
        first = next(k for k, (s, e) in enumerate(bounds) if s <= a < e or (a == e and k == len(bounds) - 1))
        last = next(k for k, (s, e) in enumerate(bounds) if s < b <= e)
        t0 = ts[first]
        before = (t0.text or "")[: a - bounds[first][0]]
        if first == last:
            after = (t0.text or "")[b - bounds[first][0]:]
            t0.text = before + repl + after
        else:
            tl = ts[last]
            tl.text = (tl.text or "")[b - bounds[last][0]:]
            t0.text = before + repl
            for k in range(first + 1, last):
                ts[k].text = ""
        t0.set(XML_SPACE, "preserve")
        for t in ts[first: last + 1]:
            t.set(XML_SPACE, "preserve")
        count += 1
    return count


def _all_paragraphs(body: ET.Element):
    return list(body.iter(W + "p"))


def _apply(pkg: Package, op: dict, state: dict) -> str:
    body = pkg.body
    kind = (op.get("op") or op.get("action") or "").strip()
    if kind == "replace_text":
        find, repl = op.get("find"), op.get("replace")
        if not find or repl is None:
            raise DocxError("replace_text needs 'find' and 'replace'")
        n = 0
        for p in _all_paragraphs(body):
            n += _replace_in_paragraph(p, str(find), str(repl), bool(op.get("match_case", True)))
            if n and op.get("all") is False:
                break
        if not n:
            raise DocxError(f"the text '{find}' was not found (the search is inside paragraphs and table cells of the body; "
                            f"it can be split by formatting, so try a shorter phrase)")
        return f"replaced {n} occurrence(s) of '{find}'"
    if kind in ("set_paragraph", "delete_paragraph", "insert_paragraph", "insert_image"):
        paras = _top_paragraphs(body)
    if kind == "set_paragraph":
        i = _pidx(paras, op.get("index"))
        p = paras[i]
        if op.get("text") is None:
            raise DocxError("set_paragraph needs 'text'")
        first_run = p.find(W + "r")
        base = first_run.find(W + "rPr") if first_run is not None else None
        ppr = p.find(W + "pPr")
        for ch in list(p):
            if ch is not ppr:
                p.remove(ch)
        if op.get("style"):
            sid = pkg.resolve_style(op["style"])
            if ppr is None:
                ppr = ET.Element(W + "pPr")
                p.insert(0, ppr)
            ps = ppr.find(W + "pStyle")
            if ps is None:
                ppr.insert(0, _el("pStyle", val=sid))
            else:
                ps.set(W + "val", sid)
        for r in _runs_from_markup(str(op["text"]), base, markup=op.get("markup", True)):
            p.append(r)
        return f"rewrote paragraph {i + 1}"
    if kind == "delete_paragraph":
        i = _pidx(paras, op.get("index"))
        p = paras[i]
        for parent in body.iter():
            if p in list(parent):
                parent.remove(p)
                break
        return f"deleted paragraph {i + 1}"
    if kind == "insert_paragraph":
        text = op.get("text")
        if text is None:
            raise DocxError("insert_paragraph needs 'text'")
        after = op.get("after", "end")
        sid = pkg.resolve_style(op["style"]) if op.get("style") else ""
        base_rpr = None
        if not sid and op.get("like") is not None:                 # copy look of an existing paragraph
            src = paras[_pidx(paras, op["like"])]
            sid = p_style(src)
            fr = src.find(W + "r")
            base_rpr = fr.find(W + "rPr") if fr is not None else None
        p = _paragraph(str(text), sid, base_rpr, markup=op.get("markup", True), align=op.get("align", ""))
        _place(body, paras, after, [p])
        return f"inserted a paragraph {_where(after)}"
    if kind == "insert_image":
        img = Path(str(op.get("path", ""))).expanduser()
        if not img.is_file():
            raise DocxError(f"image {img} not found")
        rid = pkg.add_image(img)
        state["img"] = state.get("img", 100) + 1
        p = _drawing_paragraph(rid, img, float(op.get("width_cm", 12)), state["img"], op.get("alt", img.stem), op.get("align", "center"))
        new = [p]
        if op.get("caption"):
            new.append(_paragraph(str(op["caption"]), "", _rpr(None, italic=True), align="center"))
        _place(body, paras, op.get("after", "end"), new)
        return f"inserted picture {img.name} {_where(op.get('after', 'end'))}"
    if kind == "add_table":
        rows = op.get("rows")
        if not rows or not all(isinstance(r, list) for r in rows):
            raise DocxError("add_table needs 'rows': a list of rows, each a list of cell texts")
        sid = ""
        try:
            sid = pkg.resolve_style(op.get("style") or "Table Grid", "table")
        except DocxError:
            if op.get("style"):
                raise
        tbl = _table([[str(c) for c in r] for r in rows], bool(op.get("header", True)), sid)
        paras = _top_paragraphs(body)
        _place(body, paras, op.get("after", "end"), [tbl])
        _ensure_para_after_table(body)
        return f"inserted a table {len(rows)}x{max(len(r) for r in rows)} {_where(op.get('after', 'end'))}"
    if kind in ("set_cell", "add_row"):
        tbls = _tables(body)
        ti = op.get("table")
        if not isinstance(ti, int) or not 1 <= ti <= len(tbls):
            raise DocxError(f"table must be a number 1-{len(tbls)} (tables are numbered as in docx_read: T1, T2 ...)")
        tbl = tbls[ti - 1]
        rows = tbl.findall(W + "tr")
        if kind == "set_cell":
            r, c = op.get("row"), op.get("col")
            if not (isinstance(r, int) and 1 <= r <= len(rows)):
                raise DocxError(f"row must be 1-{len(rows)}")
            cells = _cells(rows[r - 1])
            if not (isinstance(c, int) and 1 <= c <= len(cells)):
                raise DocxError(f"col must be 1-{len(cells)}")
            _set_cell(cells[c - 1], str(op.get("text", "")))
            return f"set table {ti} row {r} col {c}"
        values = op.get("cells")
        if not isinstance(values, list) or not rows:
            raise DocxError("add_row needs 'cells': a list of texts")
        new = copy.deepcopy(rows[-1])
        tcs = _cells(new)
        for k, tc in enumerate(tcs):
            _set_cell(tc, str(values[k]) if k < len(values) else "")
        pr = new.find(W + "trPr")
        if pr is not None:
            for h in pr.findall(W + "tblHeader"):
                pr.remove(h)
        tbl.insert(list(tbl).index(rows[-1]) + 1, new)
        return f"added a row to table {ti}"
    raise DocxError(f"unknown op '{kind}' (use replace_text, set_paragraph, insert_paragraph, delete_paragraph, "
                    f"insert_image, add_table, set_cell, add_row)")


def _set_cell(tc: ET.Element, text: str) -> None:
    ps = tc.findall(W + "p")
    p = ps[0] if ps else None
    if p is None:
        p = ET.SubElement(tc, W + "p")
    for extra in ps[1:]:
        tc.remove(extra)
    first_run = p.find(W + "r")
    base = first_run.find(W + "rPr") if first_run is not None else None
    ppr = p.find(W + "pPr")
    for ch in list(p):
        if ch is not ppr:
            p.remove(ch)
    for r in _runs_from_markup(text, base, markup=False):
        p.append(r)


def _pidx(paras: list[ET.Element], i) -> int:
    try:
        i = int(i)
    except (TypeError, ValueError):
        raise DocxError("index must be a paragraph number as shown by docx_read ([3] = 3)")
    if not 1 <= i <= len(paras):
        raise DocxError(f"paragraph {i} does not exist (the document has {len(paras)} paragraphs, numbered 1-{len(paras)})")
    return i - 1


def _place(body: ET.Element, paras: list[ET.Element], after, new: list[ET.Element]) -> None:
    if after in (None, "end", -1, "-1"):
        _body_insert(body, None, new)
    elif after in (0, "0", "start"):
        _body_insert(body, None, new, at_start=True)
    else:
        i = _pidx(paras, after)
        anchor = paras[i]
        # a table that directly follows the paragraph stays with the paragraph: insert right after the paragraph itself
        if anchor in list(body) or any(anchor in list(s.iter()) for s in body.findall(W + "sdt")):
            _body_insert(body, anchor, new)
        else:
            raise DocxError(f"paragraph {i + 1} is inside a table cell; use set_cell to change table content")


def _where(after) -> str:
    if after in (None, "end", -1, "-1"):
        return "at the end"
    if after in (0, "0", "start"):
        return "at the start"
    return f"after paragraph {after}"


def docx_edit(path: str, edits: list | None = None, op: str = "", index: int | None = None, text: str | None = None,
              find: str | None = None, replace: str | None = None, after=None, style: str | None = None) -> str:
    try:
        pkg = Package(Path(path).expanduser())
        ops = list(edits) if edits else []
        if not ops:
            one = {k: v for k, v in dict(op=op, index=index, text=text, find=find, replace=replace, after=after, style=style).items()
                   if v is not None and v != ""}
            if not one.get("op"):
                return "ERROR: give edits=[{op: ...}, ...] (ops: replace_text, set_paragraph, insert_paragraph, delete_paragraph, insert_image, add_table, set_cell, add_row)"
            ops = [one]
        state: dict = {}
        results = []
        for n, o in enumerate(ops, 1):
            if not isinstance(o, dict):
                return f"ERROR: edit {n} must be an object"
            try:
                msg = _apply(pkg, o, state)
            except DocxError as e:
                return f"ERROR: edit {n} ({o.get('op') or o.get('action') or '?'}): {e}. Nothing was changed."
            results.append(msg if len(ops) == 1 else f"{n}. {msg}")
        pkg.save()
        return "\n".join(results) + f"\n\n{pkg.path.name} saved ({len(_top_paragraphs(pkg.body))} paragraphs, {len(_tables(pkg.body))} tables). " \
                                    f"Re-read it with docx_read to check the result."
    except DocxError as e:
        return f"ERROR: {e}"
    except (OSError, ET.ParseError) as e:
        return f"ERROR: {e}"


# ------------------------------------------------------------------ creating
STYLES_XML = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="{WNS}">
<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:eastAsia="Calibri" w:cs="Calibri"/><w:sz w:val="22"/><w:szCs w:val="22"/><w:lang w:val="en-US" w:eastAsia="en-US" w:bidi="ar-SA"/></w:rPr></w:rPrDefault>
<w:pPrDefault><w:pPr><w:spacing w:after="160" w:line="259" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>
<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:spacing w:after="240"/></w:pPr><w:rPr><w:b/><w:color w:val="1F3864"/><w:sz w:val="48"/><w:szCs w:val="48"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="360" w:after="120"/><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/><w:color w:val="1F3864"/><w:sz w:val="32"/><w:szCs w:val="32"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="240" w:after="80"/><w:outlineLvl w:val="1"/></w:pPr><w:rPr><w:b/><w:color w:val="2F5496"/><w:sz w:val="26"/><w:szCs w:val="26"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="200" w:after="60"/><w:outlineLvl w:val="2"/></w:pPr><w:rPr><w:b/><w:color w:val="404040"/><w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="ListParagraph"><w:name w:val="List Paragraph"/><w:basedOn w:val="Normal"/><w:qFormat/><w:pPr><w:spacing w:after="60"/><w:contextualSpacing/></w:pPr></w:style>
<w:style w:type="table" w:default="1" w:styleId="TableNormal"><w:name w:val="Normal Table"/><w:tblPr><w:tblInd w:w="0" w:type="dxa"/><w:tblCellMar><w:top w:w="0" w:type="dxa"/><w:left w:w="108" w:type="dxa"/><w:bottom w:w="0" w:type="dxa"/><w:right w:w="108" w:type="dxa"/></w:tblCellMar></w:tblPr></w:style>
<w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/><w:basedOn w:val="TableNormal"/><w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/></w:pPr><w:tblPr><w:tblBorders><w:top w:val="single" w:sz="4" w:space="0" w:color="808080"/><w:left w:val="single" w:sz="4" w:space="0" w:color="808080"/><w:bottom w:val="single" w:sz="4" w:space="0" w:color="808080"/><w:right w:val="single" w:sz="4" w:space="0" w:color="808080"/><w:insideH w:val="single" w:sz="4" w:space="0" w:color="808080"/><w:insideV w:val="single" w:sz="4" w:space="0" w:color="808080"/></w:tblBorders></w:tblPr></w:style>
</w:styles>"""


def _numbering_xml(n_numbered: int) -> str:
    def lvl(i, fmt, text, left):
        return (f'<w:lvl w:ilvl="{i}"><w:start w:val="1"/><w:numFmt w:val="{fmt}"/><w:lvlText w:val="{text}"/><w:lvlJc w:val="left"/>'
                f'<w:pPr><w:ind w:left="{left}" w:hanging="360"/></w:pPr></w:lvl>')
    bullets = '<w:abstractNum w:abstractNumId="0"><w:multiLevelType w:val="hybridMultilevel"/>' + lvl(0, "bullet", "•", 720) + lvl(1, "bullet", "◦", 1440) + "</w:abstractNum>"
    numbers = ('<w:abstractNum w:abstractNumId="1"><w:multiLevelType w:val="hybridMultilevel"/>' + lvl(0, "decimal", "%1.", 720)
               + lvl(1, "lowerLetter", "%2.", 1440) + "</w:abstractNum>")
    nums = '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>'
    for k in range(n_numbered):
        nums += (f'<w:num w:numId="{k + 2}"><w:abstractNumId w:val="1"/><w:lvlOverride w:ilvl="0"><w:startOverride w:val="1"/></w:lvlOverride></w:num>')
    return f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:numbering xmlns:w="{WNS}">{bullets}{numbers}{nums}</w:numbering>'


def _parse_content(content: str, base_dir: Path, images: list):
    """Lightweight markup -> list of body elements. images collects (placeholder paragraph, path, width_cm, caption)."""
    elements: list[ET.Element] = []
    lines = content.replace("\r\n", "\n").split("\n")
    i, numbered_lists = 0, 0
    in_numbered = False
    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip()
        s = line.strip()
        if not s:
            in_numbered = False
            i += 1
            continue
        if s.startswith("|"):
            block = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                block.append(lines[i].strip())
                i += 1
            rows, header = [], False
            for b in block:
                cells = [c.strip() for c in b.strip("|").split("|")]
                if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                    header = bool(rows)
                    continue
                rows.append(cells)
            if rows:
                elements.append(_table(rows, header, "TableGrid"))
                elements.append(ET.Element(W + "p"))
            in_numbered = False
            continue
        m = re.match(r"^(#{1,3})\s+(.*)$", s)
        if m:
            elements.append(_paragraph(m.group(2), f"Heading{len(m.group(1))}"))
            in_numbered = False
            i += 1
            continue
        if s == "<<pagebreak>>":
            p = ET.Element(W + "p")
            r = ET.SubElement(p, W + "r")
            r.append(_el("br", type="page"))
            elements.append(p)
            i += 1
            continue
        m = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)(?:\{width=([\d.]+)cm\})?$", s)
        if m:
            path = Path(m.group(2)).expanduser()
            if not path.is_absolute():
                path = base_dir / path
            ph = ET.Element(W + "p")
            images.append((ph, path, float(m.group(3) or 12), m.group(1)))
            elements.append(ph)
            i += 1
            continue
        indent = len(line) - len(line.lstrip(" "))
        lvl = 1 if indent >= 2 else 0
        m = re.match(r"^[-•]\s+(.*)$", s)
        if m:
            elements.append(_paragraph(m.group(1), "ListParagraph", numid=1, ilvl=lvl))
            in_numbered = False
            i += 1
            continue
        m = re.match(r"^\d+[.)]\s+(.*)$", s)
        if m:
            if not in_numbered and lvl == 0:
                numbered_lists += 1
                in_numbered = True
            elements.append(_paragraph(m.group(1), "ListParagraph", numid=numbered_lists + 1, ilvl=lvl))
            i += 1
            continue
        in_numbered = False
        elements.append(_paragraph(s, ""))
        i += 1
    return elements, numbered_lists


def docx_create(path: str, content: str, title: str = "", overwrite: bool = False) -> str:
    p = Path(path).expanduser()
    if p.suffix.lower() != ".docx":
        return "ERROR: the file name must end with .docx"
    if p.exists() and not overwrite:
        return f"ERROR: {p} already exists. Use docx_edit to change it, or pass overwrite=true to replace it."
    if not (content or "").strip() and not title:
        return "ERROR: content is empty"
    images: list = []
    try:
        elements, n_num = _parse_content(content or "", p.parent, images)
        if title:
            elements.insert(0, _paragraph(title, "Title"))
        body = ET.Element(W + "body")
        for e in elements:
            body.append(e)
        sect = ET.SubElement(body, W + "sectPr")
        sect.append(_el("pgSz", w=11906, h=16838))
        sect.append(_el("pgMar", top=1440, right=1440, bottom=1440, left=1440, header=708, footer=708, gutter=0))
        root = ET.Element(W + "document")
        root.append(body)
        ET.register_namespace("w", WNS)
        ET.register_namespace("r", RNS)
        media: dict[str, bytes] = {}
        rels = ['<Relationship Id="rId1" Type="%s/styles" Target="styles.xml"/>' % RNS,
                '<Relationship Id="rId2" Type="%s/numbering" Target="numbering.xml"/>' % RNS]
        exts = set()
        for k, (ph, img, width, alt) in enumerate(images, 1):
            if not img.is_file():
                return f"ERROR: image {img} not found"
            ext = img.suffix.lower()
            if ext not in IMG_TYPES:
                return f"ERROR: image type {ext or '?'} is not supported (use png, jpg, gif or bmp)"
            exts.add(ext)
            name = f"image{k}{ext}"
            media["word/media/" + name] = img.read_bytes()
            rels.append(f'<Relationship Id="rId{k + 2}" Type="{RNS}/image" Target="media/{name}"/>')
            dp = _drawing_paragraph(f"rId{k + 2}", img, width, k, alt)
            ph.extend(list(dp))
        doc_xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                   + ET.tostring(root, encoding="unicode"))
        # the root needs the r: prefix declared when pictures are present
        doc_xml = doc_xml.replace(f'<w:document xmlns:w="{WNS}">', f'<w:document xmlns:w="{WNS}" xmlns:r="{RNS}">', 1)
        ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
              f'<Types xmlns="{CT_NS}"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
              '<Default Extension="xml" ContentType="application/xml"/>'
              + "".join(f'<Default Extension="{e[1:]}" ContentType="{IMG_TYPES[e]}"/>' for e in sorted(exts))
              + '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
              '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
              '<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>'
              '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
              '</Types>')
        top_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                    f'<Relationships xmlns="{PKG_REL}"><Relationship Id="rId1" Type="{RNS}/officeDocument" Target="word/document.xml"/>'
                    '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/></Relationships>')
        doc_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                    f'<Relationships xmlns="{PKG_REL}">' + "".join(rels) + "</Relationships>")
        core = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
                'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
                'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
                f'<dc:title>{_esc(title or p.stem)}</dc:title><dc:creator>Emilie</dc:creator></cp:coreProperties>')
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".emilie-tmp")
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", ct)
            z.writestr("_rels/.rels", top_rels)
            z.writestr("word/document.xml", doc_xml)
            z.writestr("word/_rels/document.xml.rels", doc_rels)
            z.writestr("word/styles.xml", STYLES_XML)
            z.writestr("word/numbering.xml", _numbering_xml(n_num))
            z.writestr("docProps/core.xml", core)
            for n, data in media.items():
                z.writestr(n, data)
        os.replace(tmp, p)
    except (OSError, ValueError) as e:
        return f"ERROR: {e}"
    paras = sum(1 for e in elements if e.tag == W + "p")
    tbls = sum(1 for e in elements if e.tag == W + "tbl")
    return (f"created {p} ({paras} paragraphs, {tbls} tables, {len(images)} pictures). "
            f"Read it back with docx_read to check it; the page layout itself is not rendered here.")


# ------------------------------------------------------------------ registry
def specs(_schema, _s, _i):
    edit_item = {"type": "object", "properties": {
        "op": {"type": "string", "enum": ["replace_text", "set_paragraph", "insert_paragraph", "delete_paragraph",
                                          "insert_image", "add_table", "set_cell", "add_row"]},
        "find": _s, "replace": _s, "match_case": {"type": "boolean"}, "all": {"type": "boolean"},
        "index": _i, "text": _s, "style": _s, "like": _i, "align": _s, "markup": {"type": "boolean"},
        "after": {"description": "paragraph number to insert after; 0 = start; 'end' = end of the document"},
        "path": _s, "width_cm": {"type": "number"}, "caption": _s, "alt": _s,
        "rows": {"type": "array", "items": {"type": "array", "items": _s}}, "header": {"type": "boolean"},
        "table": _i, "row": _i, "col": _i, "cells": {"type": "array", "items": _s}}, "required": ["op"]}
    return {
        "docx_read": (docx_read, _schema(
            "docx_read",
            "Read a Word document (.docx): paragraphs numbered [1], [2] ... with their style, list bullets and [picture] marks, "
            "tables as T1, T2 ... with rows, plus header/footer text and a note about comments or tracked changes. "
            "offset/limit page through long documents.",
            {"path": _s, "offset": _i, "limit": _i}, ["path"]), "file", False),
        "docx_edit": (docx_edit, _schema(
            "docx_edit",
            "Edit a Word document (.docx) in place, keeping its styles and everything else. Pass edits=[{op,...}, ...]: applied "
            "in order, all or nothing (indices refer to the document as it is at that step; read with docx_read first). ops: "
            "replace_text{find,replace,match_case?,all?} (works across formatting runs, in body and tables); "
            "set_paragraph{index,text,style?}; insert_paragraph{after,text,style?,like?} (style = a style that exists in the "
            "document e.g. 'Heading 1', 'List Paragraph'; like = copy the look of paragraph N; inline **bold** *italic* `code`); "
            "delete_paragraph{index}; insert_image{after,path,width_cm?,caption?}; add_table{after,rows,header?}; "
            "set_cell{table,row,col,text}; add_row{table,cells}. Not supported: tracked changes, headers/footers, text boxes.",
            {"path": _s, "edits": {"type": "array", "items": edit_item}}, ["path", "edits"]), "file", True),
        "docx_create": (docx_create, _schema(
            "docx_create",
            "Create a new Word document (.docx). content is lightweight markup, one paragraph per line: '# ', '## ', '### ' "
            "headings; '- ' bullets (indent 2 spaces for a sub-level); '1. ' numbered lists; '| a | b |' table rows (a "
            "'|---|---|' line after the first row marks it as the header); '![caption](image.png){width=12cm}' a picture; "
            "'<<pagebreak>>'; inline **bold**, *italic*, `code`. title adds a Title paragraph. A4 page, Calibri 11. "
            "Refuses to overwrite unless overwrite=true.",
            {"path": _s, "content": _s, "title": _s, "overwrite": {"type": "boolean"}}, ["path", "content"]), "file", True),
    }
