"""Validate editable draw.io XML and export through the desktop application."""
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET

from .diagrams import _RESERVED


def validate(xml):
    if not isinstance(xml, str) or not xml.strip():
        return ["xml is empty"]
    if "<!DOCTYPE" in xml:
        return ["DOCTYPE is not supported"]
    try:
        doc = ET.fromstring(xml)
    except (ValueError, ET.ParseError) as exc:
        return [str(exc)]
    errors = []
    if doc.tag != "mxfile":
        errors.append("Expected <mxfile> as root")
    pages = doc.findall("diagram")
    if not pages:
        errors.append("Missing <diagram>")
    page_ids = set()
    for i, page in enumerate(pages, 1):
        if page_id := page.get("id"):
            if page_id in page_ids:
                errors.append(f"Page {i}: duplicate diagram id {page_id!r}")
            page_ids.add(page_id)
        root = page.find("mxGraphModel/root")
        if root is None:
            errors.append(f"Page {i}: missing <mxGraphModel><root>")
            continue
        ids = set()
        cells = []
        for obj in root:
            cell = obj if obj.tag == "mxCell" else obj.find("mxCell")
            if cell is None:
                continue
            ident = obj.get("id") or cell.get("id")
            if not ident:
                errors.append(f"Page {i}: missing cell id")
            elif ident in ids:
                errors.append(f"Page {i}: duplicate id {ident!r}")
            ids.add(ident)
            cells.append((ident, cell))
        for required in ("0", "1"):
            if required not in ids:
                errors.append(f"Page {i}: missing cell id {required}")
        for ident, cell in cells:
            for attr in ("source", "target", "parent"):
                if attr in cell.attrib and cell.get(attr) not in ids:
                    errors.append(f"Page {i}, cell {ident!r}: unknown {attr} {cell.get(attr)!r}")
    return errors


def executable():
    if override := os.getenv("DRAWIO_PATH"):
        return shutil.which(override)
    for candidate in (r"C:\Program Files\draw.io\draw.io.exe", "drawio", "draw.io"):
        if found := shutil.which(candidate):
            return found


def render_drawio(xml, filename, fmt="png", scale=2):
    try:
        errors = validate(xml)
        if errors:
            raise ValueError("\n".join(errors))
        if not isinstance(filename, str) or not re.fullmatch(r"[\w -][\w .-]{0,119}", filename) or filename.endswith((" ", ".")) or _RESERVED.fullmatch(filename):
            raise ValueError("Invalid filename: use a plain filename without a directory")
        stem = filename.removesuffix(".drawio")
        if fmt not in ("png", "svg", "pdf"):
            raise ValueError("fmt must be png, svg or pdf")
        if isinstance(scale, bool) or not isinstance(scale, (int, float)) or not math.isfinite(scale) or scale <= 0:
            raise ValueError("scale must be a finite positive number")
        cli = executable()
        if not cli:
            raise ValueError("draw.io Desktop not found. Install with winget install JGraph.Draw or set DRAWIO_PATH.")
        folder = Path.cwd() / "diagrams"
        folder.mkdir(exist_ok=True)
        if folder.resolve() != folder:
            raise ValueError("diagrams must not point outside the project")
        source = folder / (stem + ".drawio")
        dest = folder / (stem + "." + fmt)
        with tempfile.TemporaryDirectory(dir=folder) as directory:
            tmp = Path(directory)
            src = tmp / source.name
            src.write_text(xml, encoding="utf-8")
            outputs = [src]
            for ext in dict.fromkeys((fmt, "png")):
                out = tmp / (stem + "." + ext)
                result = subprocess.run([cli, "-x", "-f", ext, "-s", str(scale), "-b", "10", "-o", str(out), str(src)],
                                        capture_output=True, text=True, errors="replace", timeout=90)
                if result.returncode or not out.is_file() or not out.stat().st_size:
                    raise ValueError((result.stderr or result.stdout).strip() or f"draw.io did not export {ext} (exit {result.returncode})")
                outputs.append(out)
            for file in outputs:
                file.replace(folder / file.name)
        return json.dumps(dict(ok=True, drawio_path=str(source), image_path=str(dest)))
    except (OSError, ValueError, OverflowError, subprocess.TimeoutExpired) as exc:
        return json.dumps(dict(ok=False, error=str(exc)))


def specs(schema, string):
    return {"render_drawio": (render_drawio, schema("render_drawio",
        "Export complete draw.io xml with filename, fmt (png/svg/pdf), and scale (default 2). Inspect the sibling PNG using read_file and correct layout issues.",
        {"xml": string, "filename": string, "fmt": {"type": "string", "enum": ["png", "svg", "pdf"]},
         "scale": {"type": "number"}}, ["xml", "filename"]), "file", True)}
