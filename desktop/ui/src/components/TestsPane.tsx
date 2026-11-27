// The Tests panel: the project's test suites (pytest, unittest, Vitest, Jest, go test, cargo test, npm test) run with
// one click, read back test by test. Failed ones first, each with why it failed; open it at its line, run it alone, or
// hand it to Emilie. "Run failed" runs only what failed last time. For Python, the interpreter can be chosen.
import { useEffect, useMemo, useState } from "react";
import { get, post } from "@/lib/api";
import { useStore } from "@/lib/store";
import { cn } from "@/lib/util";
import * as I from "./icons";
import {
  agoSecs, askEmilie, btnPrimary, btnSm, Card, Chevron, copy, Empty, fence, Heading, Hint, Output, Pill, plural, remember,
  RowBtn, rowCls, SearchField, splitPath, stripAnsi, took, useJob,
} from "./PaneKit";
import { Menu, MenuContent, MenuItem, MenuLabel, MenuTrigger, Spinner } from "./ui";

interface Suite { id: string; kind: string; label: string; dir: string; cmd: string }
interface Py { path: string; label: string }
interface Test { id: string; name: string; suite: string; file: string; abs: string; line: number; status: "passed" | "failed" | "skipped"; secs: number; message: string; output: string }
interface Result { suite: string; kind: string; tests: Test[]; summary: { passed: number; failed: number; skipped: number; total: number; secs: number }; code: number; tail: string; error: string; only: boolean; at: number }
type Filter = "all" | "failed" | "passed" | "skipped";

interface Mem { suite: string; job: string | null; result: Result | null; filter: Filter; q: string }
const mem = new Map<string, Mem>();
const STATUS_ICON = {
  passed: <I.Check size={12} className="shrink-0 text-ok" />,
  failed: <I.X size={12} className="shrink-0 text-danger" />,
  skipped: <I.CircleSlash size={11} className="shrink-0 text-text-500" />,
};

export function TestsPane({ cwd }: { cwd: string }) {
  const m = remember(mem, cwd, (): Mem => ({ suite: "", job: null, result: null, filter: "all", q: "" }));
  const toast = useStore((s) => s.toast);
  const pyKey = "emilie.tests.python:" + cwd;
  const [suites, setSuites] = useState<Suite[] | null>(null);
  const [pythons, setPythons] = useState<Py[]>([]);
  const [python, setPythonState] = useState(() => { try { return localStorage.getItem(pyKey) || ""; } catch { return ""; } });
  const [suite, setSuiteState] = useState(m.suite);
  const [err, setErr] = useState("");
  const [jobId, setJobId] = useState<string | null>(m.job);
  const [result, setResult] = useState<Result | null>(m.result);
  const [filter, setFilter] = useState<Filter>(m.filter);
  const [q, setQ] = useState(m.q);
  const [open, setOpen] = useState("");
  const [shut, setShut] = useState<Record<string, boolean>>({});
  const [out, setOut] = useState(false);
  useEffect(() => { m.filter = filter; m.q = q; }, [filter, q]);   // eslint-disable-line react-hooks/exhaustive-deps

  const detect = (py = python) => get<{ suites: Suite[]; pythons: Py[] }>("/api/tests/suites", { cwd, python: py })
    .then((r) => {
      setSuites(r.suites);
      setPythons(r.pythons);
      setErr("");
      if (!r.suites.some((s) => s.id === m.suite) && r.suites[0]) { m.suite = r.suites[0].id; setSuiteState(r.suites[0].id); }
    }).catch((e) => setErr(e.message));
  useEffect(() => { if (cwd) detect(); }, [cwd]);   // eslint-disable-line react-hooks/exhaustive-deps
  const setPython = (p: string) => {
    setPythonState(p);
    try { localStorage.setItem(pyKey, p); } catch { /* private window */ }
    detect(p);                                           // pytest may be installed in one and not the other
  };
  const setSuite = (id: string) => { m.suite = id; setSuiteState(id); };

  const { job, lines } = useJob<Result>(jobId, (j) => {
    m.job = null;
    if (j.result) {
      const r = j.result;
      // a run of some tests updates those in the last full run, so the list stays whole
      const merged = r.only && result && result.suite === r.suite
        ? { ...r, only: false, tests: result.tests.map((t) => r.tests.find((x) => x.id === t.id) || t).concat(r.tests.filter((x) => !result.tests.some((t) => t.id === x.id))) }
        : r;
      if (r.only) merged.summary = summarize(merged.tests, r.summary.secs);
      m.result = merged;
      setResult(merged);
      if (r.summary.failed) setFilter((f) => (f === "passed" ? "all" : f));
      if (r.error) setOut(true);
    }
    if (j.error && j.error !== "Stopped") toast(j.error, "error");
  });
  const running = !!job?.running || (!!jobId && !job);

  const start = async (only: string[] = []) => {
    if (!suite) return;
    try {
      const r = await post<{ job: string }>("/api/tests/run", { cwd, suite, python, only });
      m.job = r.job;
      setJobId(r.job);
      setOut(false);
    } catch (e: any) {
      toast(e.message, "error");
    }
  };

  const tests = result && result.suite === suite ? result.tests : [];
  const failed = tests.filter((t) => t.status === "failed");
  const groups = useMemo(() => {
    const ql = q.trim().toLowerCase();
    const shown = tests.filter((t) => (filter === "all" || t.status === filter) && (!ql || t.name.toLowerCase().includes(ql) || t.file.toLowerCase().includes(ql) || t.suite.toLowerCase().includes(ql)));
    const by = new Map<string, Test[]>();
    for (const t of shown) { const k = t.file || t.suite || "(tests)"; const l = by.get(k) || []; l.push(t); by.set(k, l); }
    const rank = (ts: Test[]) => (ts.some((t) => t.status === "failed") ? 0 : 1);
    return [...by.entries()].map(([file, ts]) => ({ file, ts: ts.sort((a, b) => (a.status === "failed" ? 0 : 1) - (b.status === "failed" ? 0 : 1) || a.line - b.line) }))
      .sort((a, b) => rank(a.ts) - rank(b.ts) || a.file.localeCompare(b.file));
  }, [tests, filter, q]);

  const fixOne = (t: Test) => askEmilie(
    `The test ${t.id} fails${t.file ? ` (${t.file}${t.line ? `:${t.line}` : ""})` : ""}:\n${fence(t.message || t.output || "(no message)", 2500)}\n` +
    "Find out whether the code or the test is wrong, fix the right one, and run that test again to show it passes.");
  const fixAll = () => askEmilie(
    `${plural(failed.length, "test")} fail${failed.length === 1 ? "s" : ""}:\n` +
    failed.slice(0, 25).map((t) => `- ${t.id}: ${stripAnsi(t.message).split("\n").find((l) => l.trim())?.slice(0, 200) || "failed"}`).join("\n") +
    (failed.length > 25 ? `\n(and ${failed.length - 25} more)` : "") + "\nFix them (decide each time whether the code or the test is wrong), then run the tests again.");

  if (!cwd) return <Empty icon={<I.Flask size={22} />} title="No folder">Open a session in a folder to run its tests.</Empty>;
  if (suites && !suites.length) {
    return (
      <Empty icon={<I.Flask size={22} />} title="No tests found"
        action={<button className={btnPrimary} onClick={() => askEmilie("Set up a test framework for this project (the usual one for its language) with a first test of its most important function, and tell me how to run the tests.")}>Ask Emilie to add tests</button>}>
        Emilie looks for pytest and unittest (a tests folder), Vitest and Jest (package.json), go test and cargo test, and a package.json test script.
      </Empty>
    );
  }
  const cur = suites?.find((s) => s.id === suite);
  const isPy = cur?.kind === "pytest" || cur?.kind === "unittest";
  const sum = result && result.suite === suite ? result.summary : null;

  return (
    <div className="flex h-full flex-col text-[11.5px]">
      <div className="border-b border-border-300 px-2.5 pb-2 pt-2 dark:border-[#353535]">
        <div className="flex flex-wrap items-center gap-1.5">
          {running
            ? <button className={cn(btnSm, "hover:text-danger")} onClick={() => post("/api/job/stop", { id: jobId })}><I.Square size={9} />Stop</button>
            : <button className={btnPrimary} disabled={!cur} onClick={() => start()}><I.Play size={11} />Run all</button>}
          {!running && !!failed.length && <button className={btnSm} onClick={() => start(failed.map((t) => t.id))}><I.RotateCw size={10} />Run failed ({failed.length})</button>}
          {(suites?.length || 0) > 1 && (
            <Menu>
              <MenuTrigger asChild>
                <button className="flex h-[22px] min-w-0 items-center gap-1 rounded-[5px] px-1.5 text-[11px] text-text-200 hover:bg-hover"><span className="truncate">{cur?.label || "Suite"}</span><I.ChevD size={9} /></button>
              </MenuTrigger>
              <MenuContent align="start">
                {suites!.map((s) => <MenuItem key={s.id} checked={s.id === suite} shortcut={s.cmd} onSelect={() => setSuite(s.id)}>{s.label}</MenuItem>)}
              </MenuContent>
            </Menu>
          )}
          {suites?.length === 1 && <span className="truncate text-[11px] text-text-400" title={cur?.cmd}>{cur?.label}</span>}
          {isPy && pythons.length > 0 && (
            <Menu>
              <MenuTrigger asChild>
                <button title="The Python the tests run with" className="flex h-[22px] min-w-0 max-w-[160px] items-center gap-1 rounded-[5px] px-1.5 text-[11px] text-text-400 hover:bg-hover hover:text-text-100">
                  <I.CodeBrackets size={11} className="shrink-0" /><span className="truncate">{(pythons.find((p) => p.path === python) || pythons[0]).label.replace(/ \(.*\)$/, "").split(/[\\/]/).slice(-3).join("/")}</span><I.ChevD size={9} className="shrink-0" />
                </button>
              </MenuTrigger>
              <MenuContent align="start" className="max-w-[420px]">
                <MenuLabel>Run the tests with</MenuLabel>
                {pythons.map((p) => <MenuItem key={p.path} checked={(python || pythons[0].path) === p.path} onSelect={() => setPython(p.path)}>{p.label}</MenuItem>)}
              </MenuContent>
            </Menu>
          )}
          <span className="flex-1" />
          {!running && !!failed.length && <button className={btnSm} onClick={fixAll}><I.Sparkles size={11} />Fix with Emilie</button>}
        </div>
        {(sum || running) && (
          <div className="mt-2">
            <div className="flex items-center gap-2 text-[11px]">
              {running ? <span className="flex items-center gap-1.5 text-text-400"><Spinner size={11} />Running… {job ? took(job.secs) : ""}</span> : sum && (
                <>
                  <span className="text-ok">{sum.passed} passed</span>
                  {!!sum.failed && <span className="text-danger">{sum.failed} failed</span>}
                  {!!sum.skipped && <span className="text-text-500">{sum.skipped} skipped</span>}
                  <span className="text-text-500">· {took(sum.secs)} · {agoSecs(result!.at)}</span>
                </>
              )}
            </div>
            {sum && sum.total > 0 && !running && (
              <div className="mt-1.5 flex h-[4px] overflow-hidden rounded-full bg-bg-400">
                <div className="bg-ok" style={{ width: `${(sum.passed / sum.total) * 100}%` }} />
                <div className="bg-danger" style={{ width: `${(sum.failed / sum.total) * 100}%` }} />
              </div>
            )}
          </div>
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2.5 pb-3">
        {err && <div className="mt-2 text-[11px] text-danger">{err}</div>}
        {!suites && !err && <div className="p-2"><Spinner /></div>}
        {suites && !tests.length && !running && !result?.error && <Hint className="mt-3">Press Run all to run {cur?.cmd ? <code className="font-mono text-[10.5px]">{cur.cmd}</code> : "the tests"}{cur?.dir ? ` in ${cur.dir}` : ""}.</Hint>}
        {result?.error && result.suite === suite && !running && (
          <div className="mt-2 flex items-center gap-2 rounded-[8px] bg-warn-soft px-2.5 py-1.5 text-[11px] text-warn">
            <I.Alert size={12} className="shrink-0" /><span className="min-w-0 flex-1">{result.error}</span>
            <button className="shrink-0 underline-offset-2 hover:underline" onClick={() => askEmilie(`Running the tests (${cur?.cmd}) did not work. The end of the output:\n${fence(result.tail, 2500)}\nFind out why and fix it.`)}>Ask Emilie</button>
          </div>
        )}
        {!!tests.length && (
          <div className="mt-2 flex flex-wrap items-center gap-1">
            {(["all", "failed", "passed", "skipped"] as Filter[]).map((f) => (
              <Pill key={f} on={filter === f} onClick={() => setFilter(f)}>
                {f === "all" ? "All" : STATUS_ICON[f]}<span className="tabular-nums">{f === "all" ? tests.length : tests.filter((t) => t.status === f).length}</span>
              </Pill>
            ))}
            <div className="ml-1 flex min-w-[120px] flex-1"><SearchField value={q} onChange={setQ} placeholder="Filter tests" /></div>
          </div>
        )}
        {!!tests.length && !groups.length && <Hint className="mt-3">Nothing matches this filter.</Hint>}

        <div className="mt-2 flex flex-col gap-2">
          {groups.map(({ file, ts }) => {
            const on = !shut[file];
            const [name, dir] = splitPath(file);
            const bad = ts.filter((t) => t.status === "failed").length;
            return (
              <Card key={file}>
                <div role="button" onClick={() => setShut((s) => ({ ...s, [file]: on }))} className={cn(rowCls, "py-[6px]")}>
                  <Chevron on={on} />
                  <span className="max-w-[60%] shrink-0 truncate text-text-100">{name}</span>
                  <span className="min-w-0 flex-1 truncate text-[10.5px] text-text-500">{dir}</span>
                  {!running && <RowBtn tip="Run this file's tests" onClick={() => start(ts.map((t) => t.id))}><I.Play size={10} /></RowBtn>}
                  <span className={cn("shrink-0 tabular-nums text-[10.5px]", bad ? "text-danger" : "text-text-500")}>{bad ? `${bad}/${ts.length}` : ts.length}</span>
                </div>
                {on && (
                  <div className="border-t border-border-200">
                    {ts.slice(0, 300).map((t, i) => {
                      const isOpen = open === t.id;
                      return (
                        <div key={t.id} className={cn(i > 0 && "border-t border-border-200")}>
                          <div role="button" onClick={() => setOpen(isOpen ? "" : t.id)} title={t.id} className={cn(rowCls, "h-[24px] gap-1.5 pl-[12px] pr-2.5")}>
                            {STATUS_ICON[t.status]}
                            <span className={cn("min-w-0 flex-1 truncate", t.status === "failed" ? "text-text-100" : "text-text-300")}>
                              {t.suite && t.suite !== name.replace(/\.\w+$/, "") && <span className="text-text-500">{t.suite} › </span>}{t.name}
                            </span>
                            {!running && <RowBtn tip="Run this test" onClick={() => start([t.id])}><I.Play size={10} /></RowBtn>}
                            {t.secs > 0.0005 && <span className={cn("shrink-0 tabular-nums text-[10px]", t.secs > 1 ? "text-warn" : "text-text-500")}>{took(t.secs)}</span>}
                          </div>
                          {isOpen && (
                            <div className="border-t border-border-200 bg-bg-100">
                              {t.message ? <pre className={cn("max-h-[300px] overflow-auto whitespace-pre-wrap break-words px-3 py-2 font-mono text-[10.5px] leading-[15px] selectable", t.status === "failed" ? "text-danger" : "text-text-300")}>{stripAnsi(t.message)}</pre>
                                : <div className="px-3 py-2 text-[11px] text-text-500">{t.status === "passed" ? "Passed." : "No details."}</div>}
                              {t.output && t.status === "failed" && <Output lines={t.output.split("\n")} className="max-h-[160px] border-t border-border-200" />}
                              <div className="flex flex-wrap gap-1.5 border-t border-border-200 px-3 py-2">
                                {t.abs && <button className={btnSm} onClick={() => useStore.getState().openFile(t.abs, t.line || undefined)}><I.External size={10} />Open{t.line ? ` at line ${t.line}` : ""}</button>}
                                {t.status === "failed" && <button className={btnSm} onClick={() => fixOne(t)}><I.Sparkles size={11} />Fix with Emilie</button>}
                                {!!t.message && <button className={btnSm} onClick={() => copy(stripAnsi(t.message), "Copied")}><I.Copy size={10} />Copy</button>}
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })}
                    {ts.length > 300 && <div className="border-t border-border-200 py-[4px] pl-[32px] text-[10.5px] text-text-500">and {ts.length - 300} more</div>}
                  </div>
                )}
              </Card>
            );
          })}
        </div>

        {(running || lines.length > 0 || result?.tail) && (
          <>
            <Heading title="Output" open={out || running} onToggle={() => setOut(!out)} />
            {(out || running) && <Card><Output lines={lines.length ? lines : (result?.tail || "").split("\n")} /></Card>}
          </>
        )}
      </div>
    </div>
  );
}

function summarize(tests: Test[], secs: number): Result["summary"] {
  const s = { passed: 0, failed: 0, skipped: 0, total: tests.length, secs };
  for (const t of tests) s[t.status] += 1;
  return s;
}
