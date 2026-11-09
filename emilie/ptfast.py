"""Pure-speed patches for prompt_toolkit. Output is byte-for-byte identical; only repeated work is cached."""
from __future__ import annotations

import functools


def install() -> None:
    """The banner video produces a style string per cell ('fg:#rrggbb bg:#rrggbb'), almost all new every frame, so
    prompt_toolkit re-parses them constantly. The parse of one part is a pure function (str -> immutable Attrs), so we
    memoise it: colours repeat across cells/frames even when the full strings do not."""
    from prompt_toolkit.styles import style as _style
    fn = _style._parse_style_str
    if getattr(fn, "_emilie_cached", False):
        return
    cached = functools.lru_cache(maxsize=16384)(fn)
    cached._emilie_cached = True                  # type: ignore[attr-defined]
    _style._parse_style_str = cached
    _patch_style_lookup(_style)


def _patch_style_lookup(_style) -> None:
    """Style.get_attrs_for_style_str builds a list and runs 10 'first non-None from the end' scans per call. For a
    string made only of inline parts (no 'class:'), the result is simply: the merged defaults, overridden field by
    field by each part in order. Same result, a fraction of the work. Strings with 'class:' use the original code."""
    Style = _style.Style
    orig = Style.get_attrs_for_style_str
    if getattr(orig, "_emilie_fast", False):
        return
    parse = _style._parse_style_str
    merge = _style._merge_attrs
    base_cache: dict = {}

    def fast(self, style_str, default=_style.DEFAULT_ATTRS):
        if "class:" in style_str:
            return orig(self, style_str, default)
        key = (id(self.class_names_and_attrs), id(default))
        hit = base_cache.get(key)
        if hit is None or hit[0] is not self.class_names_and_attrs:
            if len(base_cache) > 8:
                base_cache.clear()
            base = merge([default] + [a for names, a in self.class_names_and_attrs if not names])
            hit = base_cache[key] = (self.class_names_and_attrs, base)
        cur = hit[1]
        for part in style_str.split():
            a = parse(part)
            cur = type(cur)(*[n if n is not None else o for o, n in zip(cur, a)])
        return cur

    fast._emilie_fast = True                       # type: ignore[attr-defined]
    fast._orig = orig                              # type: ignore[attr-defined]
    Style.get_attrs_for_style_str = fast


def trim_renderer_caches(app, limit: int = 40000) -> None:
    """Renderer._attrs_for_style is a dict that only grows (one entry per distinct style string ever drawn), which is
    a slow memory leak with an animated truecolor banner. Emptying it is harmless: entries are rebuilt on demand.

    This runs on the refresh THREAD while the event-loop thread may be in the middle of Renderer.render(), which reads
    `_style_string_has_style` AFTER the (slow) write_to_screen. Setting those attributes to None here made render pass
    None to the screen diff -> "TypeError: 'NoneType' object is not subscriptable" and a crash dialog. So the attributes
    are never replaced: both caches are dicts with __missing__, and dict.clear() is atomic and always safe to read."""
    r = getattr(app, "renderer", None)
    c = getattr(r, "_attrs_for_style", None)
    if c is not None and len(c) > limit:
        h = getattr(r, "_style_string_has_style", None)
        c.clear()
        if h is not None:
            h.clear()


def tune_gc() -> None:
    """Every frame allocates many short-lived tuples/lists, which made the cyclic GC run (and sometimes pause 30-70 ms)
    in the middle of an animation. Freeze what exists at startup (modules, tables) and collect young objects less
    often. Memory is not affected in any way you can notice; frame pacing gets much steadier."""
    import gc
    gc.collect()
    gc.freeze()
    gc.set_threshold(30000, 20, 50)
