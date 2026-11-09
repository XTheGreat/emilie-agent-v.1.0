"""Stand-alone notebook runner used by notebook_run. Standard library only, so it works in ANY user Python (3.8+).

    python nbrun.py <notebook> <output> <cells> <allow_errors 0|1> <timeout seconds>

Executes the code cells in one shared namespace, in order, and writes the outputs back (stream text, the value of the last
expression, rich display of objects with _repr_png_/_repr_html_, matplotlib figures as PNG, errors with a traceback).
Not supported: % and %% magics (a few harmless ones are ignored), ! shell lines, interactive widgets, input().
Prints a short per-cell summary. Exit code 0 = all cells ran, 1 = a cell failed or the time limit was hit.
"""
import ast
import base64
import contextlib
import io
import json
import linecache
import os
import sys
import threading
import time
import traceback

IGNORED_MAGICS = ("%matplotlib", "%load_ext", "%reload_ext", "%autoreload", "%config", "%pylab", "%env", "%precision", "%pprint")


def parse_cells(spec, n):
    if not spec.strip():
        return None
    out = set()
    for part in spec.replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            lo, hi = int(a or 1), int(b or n)
            out.update(range(lo, hi + 1))
        else:
            out.add(int(part))
    bad = [i for i in out if not 1 <= i <= n]
    if bad:
        raise ValueError(f"cell(s) {sorted(bad)} out of range 1-{n}")
    return sorted(out)


def lines_of(text):
    return text.splitlines(keepends=True)


def rich(obj):
    """MIME bundle for an object, like IPython's display."""
    data = {}
    try:
        png = getattr(obj, "_repr_png_", None)
        if callable(png):
            b = png()
            if isinstance(b, bytes):
                data["image/png"] = base64.b64encode(b).decode("ascii")
        html = getattr(obj, "_repr_html_", None)
        if callable(html):
            h = html()
            if isinstance(h, str):
                data["text/html"] = lines_of(h)
    except Exception:
        pass
    if "image/png" not in data and type(obj).__name__ == "Image" and hasattr(obj, "save"):      # PIL.Image
        try:
            buf = io.BytesIO()
            obj.save(buf, format="PNG")
            data["image/png"] = base64.b64encode(buf.getvalue()).decode("ascii")
        except Exception:
            pass
    data["text/plain"] = lines_of(repr(obj))
    return data


def figures(outs):
    plt = sys.modules.get("matplotlib.pyplot")
    if plt is None:
        return 0
    n = 0
    try:
        for num in list(plt.get_fignums()):
            fig = plt.figure(num)
            buf = io.BytesIO()
            fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
            outs.append({"output_type": "display_data", "metadata": {},
                         "data": {"image/png": base64.b64encode(buf.getvalue()).decode("ascii"),
                                  "text/plain": ["<Figure size %dx%d>" % tuple(int(v * fig.dpi) for v in fig.get_size_inches())]}})
            n += 1
        plt.close("all")
    except Exception as e:
        outs.append({"output_type": "stream", "name": "stderr", "text": [f"(could not capture the figures: {e})\n"]})
    return n


def prepare(src, notes):
    """Drop magics/shell lines that cannot work here; return the runnable source."""
    out = []
    for i, line in enumerate(src.splitlines()):
        s = line.strip()
        if s.startswith("%%"):
            if i == 0 and s.split()[0] in ("%%time", "%%timeit", "%%capture", "%%script"):
                notes.append(f"ignored {s.split()[0]}")
                out.append("")
                continue
            raise RuntimeError(f"cell magic {s.split()[0]} is not supported by the built-in runner")
        if s.startswith("%"):
            notes.append(f"ignored magic line: {s[:50]}")
            out.append("" if line[: len(line) - len(line.lstrip())] == "" else line[: len(line) - len(line.lstrip())] + "pass")
            continue
        if s.startswith("!"):
            notes.append(f"skipped shell line: {s[:50]}")
            out.append(line[: len(line) - len(line.lstrip())] + "pass")
            continue
        out.append(line)
    return "\n".join(out) + "\n"


def run_cell(src, ns, fname, count, outs):
    notes = []
    code_src = prepare(src, notes)
    linecache.cache[fname] = (len(code_src), None, lines_of(code_src), fname)
    tree = last = None
    parse_error = None
    try:
        tree = ast.parse(code_src, fname, "exec")
        if tree.body and isinstance(tree.body[-1], ast.Expr):
            last = ast.Expression(tree.body.pop().value)
    except SyntaxError as e:
        parse_error = e
    so, se = io.StringIO(), io.StringIO()
    error = parse_error
    value = None
    try:
        if parse_error is not None:
            raise parse_error
        with contextlib.redirect_stdout(so), contextlib.redirect_stderr(se):
            exec(compile(tree, fname, "exec"), ns)
            value = eval(compile(last, fname, "eval"), ns) if last is not None else None
    except BaseException as e:          # incl. SystemExit/KeyboardInterrupt from user code
        error = e
        value = None
    if so.getvalue():
        outs.append({"output_type": "stream", "name": "stdout", "text": lines_of(so.getvalue())})
    if se.getvalue():
        outs.append({"output_type": "stream", "name": "stderr", "text": lines_of(se.getvalue())})
    nfig = figures(outs)
    if error is None and value is not None:
        outs.append({"output_type": "execute_result", "execution_count": count, "metadata": {}, "data": rich(value)})
    if error is not None:
        if isinstance(error, SyntaxError):
            tb = traceback.format_exception_only(type(error), error)
        else:
            tb = traceback.format_exception(type(error), error, error.__traceback__.tb_next if error.__traceback__ else None)
        outs.append({"output_type": "error", "ename": type(error).__name__, "evalue": str(error),
                     "traceback": [l.rstrip("\n") for l in "".join(tb).splitlines()]})
    return error, nfig, notes


def main():
    real_out = sys.stdout                 # user code runs under redirect_stdout; the runner's own messages must not be captured
    nb_path, out_path, spec, allow, limit = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4] == "1", float(sys.argv[5])
    with open(nb_path, encoding="utf-8") as f:
        nb = json.load(f)
    cells = nb["cells"]
    try:
        chosen = parse_cells(spec, len(cells))
    except ValueError as e:
        print(f"ERROR: {e}")
        return 1
    order = [i for i in (chosen if chosen is not None else range(1, len(cells) + 1)) if cells[i - 1].get("cell_type") == "code"]
    for i in order:                                    # clear only the cells that will run
        cells[i - 1]["outputs"] = []
        cells[i - 1]["execution_count"] = None
    os.chdir(os.path.dirname(os.path.abspath(nb_path)) or ".")
    sys.path.insert(0, os.getcwd())
    ns = {"__name__": "__main__", "__builtins__": __builtins__}

    def display(*objs):
        for o in objs:
            current.append({"output_type": "display_data", "metadata": {}, "data": rich(o)})
    ns["display"] = display

    def save():
        text = json.dumps(nb, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
        tmp = out_path + ".emilie-tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, out_path)

    state = {"cell": 0}

    def watchdog():
        try:
            save()
        finally:
            real_out.write(f"TIMEOUT: the run hit the {int(limit)}s limit while executing cell {state['cell']}; "
                           f"outputs of the cells that finished were saved to {out_path}\n")
            real_out.flush()
            os._exit(1)
    timer = threading.Timer(limit, watchdog)
    timer.daemon = True
    timer.start()

    count, lines, failed, allnotes = 0, [], None, []
    current = []
    t_all = time.time()
    for i in order:
        c = cells[i - 1]
        state["cell"] = i
        count += 1
        current = c["outputs"] = []
        t0 = time.time()
        src = "".join(c["source"]) if isinstance(c.get("source"), list) else str(c.get("source", ""))
        try:
            err, nfig, notes = run_cell(src, ns, f"<cell {i}>", count, current)
        except RuntimeError as e:
            err, nfig, notes = e, 0, []
            current.append({"output_type": "error", "ename": "UnsupportedMagic", "evalue": str(e), "traceback": [str(e)]})
        c["execution_count"] = count
        allnotes += [f"cell {i}: {n}" for n in notes]
        dt = time.time() - t0
        text = ""
        for o in current:
            if o["output_type"] == "stream" and o["name"] == "stdout":
                text = "".join(o["text"]).strip().splitlines()[0:1] and "".join(o["text"]).strip().splitlines()[0]
                break
            if o["output_type"] == "execute_result":
                text = "".join(o["data"]["text/plain"]).strip().splitlines()[0] if o["data"].get("text/plain") else ""
                break
        extra = f" [+{nfig} figure{'s' if nfig != 1 else ''}]" if nfig else ""
        if err is not None:
            e = current[-1]
            lines.append(f"cell {i} FAILED ({dt:.1f}s): {e.get('ename')}: {e.get('evalue')}\n    " + "\n    ".join(e.get("traceback", [])[-6:]))
            failed = i
            if not allow:
                break
        else:
            lines.append(f"cell {i} ok ({dt:.1f}s){extra}" + (f": {text[:100]}" if text else ""))
    timer.cancel()
    save()
    done = sum(1 for _ in lines)
    print("\n".join(lines))
    if allnotes:
        print("notes: " + "; ".join(allnotes[:8]))
    skipped = [i for i in order if i > (failed or 0)] if failed and not allow else []
    print(f"Ran {done} of {len(order)} code cell(s) in {time.time() - t_all:.1f}s with the built-in runner; saved to {out_path}"
          + (f". Stopped at the first error; {len(skipped)} later cell(s) were not run." if skipped else "."))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
