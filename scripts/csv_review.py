#!/usr/bin/env python3
"""Quickly screen and mark a weekly discovery CSV in a local browser page.

Usage:
  python3 scripts/csv_review.py discovery/weekly/2026/08/idr_2026-08-31.csv \
      [--port 8000] [--no-browser]

The script embeds the CSV rows into a self-contained HTML page, serves it on
localhost, and writes per-repo marks back to the CSV's trailing `mark` column
when you hit "保存标注". Marks are stored as ✅/⏸/❌ (eye-catching when the CSV
is opened by hand), keyed by fullName, and survive across sessions because
they live in the CSV itself.
"""
import argparse
import csv
import json
import os
import sys
import tempfile
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse


def load_csv(path):
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        return [], []
    return rows[0], rows[1:]


# The mark column stores the emoji directly (eye-catching when opening the CSV
# by hand); internally the page uses short codes. Converted at the CSV boundary.
MARK_CSV = {"yes": "✅", "later": "⏸", "no": "❌"}
MARK_CODE = {v: k for k, v in MARK_CSV.items()}


def get_marks(columns, rows):
    fn = columns.index("fullName") if "fullName" in columns else 0
    mk = columns.index("mark") if "mark" in columns else -1
    out = {}
    for r in rows:
        name = r[fn] if fn < len(r) else ""
        if not name:
            continue
        mark = r[mk] if 0 <= mk < len(r) else ""
        if mark:
            out[name] = MARK_CODE.get(mark, mark)
    return out


def apply_marks(path, marks, tmp_dir=None):
    """Rewrite path with a trailing `mark` column; return (total_rows, changed_rows).

    Only cells listed in marks are touched; everything else is preserved
    byte-for-byte. The write is atomic (temp file in the same directory,
    then os.replace) so a crash never leaves a half-written CSV.
    """
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        return 0, 0
    columns = rows[0]
    fn = columns.index("fullName") if "fullName" in columns else 0
    mk = columns.index("mark") if "mark" in columns else -1
    if mk == -1:
        columns.append("mark")
        mk = len(columns) - 1
        for r in rows[1:]:
            r.append("")
    updated = 0
    for r in rows[1:]:
        name = r[fn] if fn < len(r) else ""
        if name in marks:
            want = MARK_CSV.get(marks[name], marks[name])  # code -> emoji
            if MARK_CODE.get(r[mk], r[mk]) != marks[name]:  # normalize legacy values
                r[mk] = want
                updated += 1
    base = tmp_dir or os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=base, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            # Pin \n explicitly: csv's default lineterminator changed \r\n -> \n
            # in Python 3.14; pinning keeps the file identical on any version.
            csv.writer(f, lineterminator="\n").writerows(rows)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return len(rows) - 1, updated


# Raw string: the JS inside contains \n / \t escapes that must reach the
# browser literally (e.g. lines.join("\n")); a normal string would turn them
# into real newline/tab characters and break the script.
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CSV Review</title>
<style>
  body { font-family: system-ui, "PingFang SC", "Microsoft YaHei", sans-serif; margin: 0; background: #f5f6f8; color: #1f2328; }
  #toolbar { position: sticky; top: 0; background: #fff; border-bottom: 1px solid #d0d7de; padding: 8px 12px; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; z-index: 10; }
  #q { padding: 5px 8px; border: 1px solid #d0d7de; border-radius: 6px; width: 240px; }
  .chip { border: 1px solid #d0d7de; background: #f6f8fa; border-radius: 20px; padding: 3px 10px; cursor: pointer; font-size: 13px; user-select: none; }
  .chip.on { background: #0969da; color: #fff; border-color: #0969da; }
  #coltoggles label { font-size: 12px; color: #57606a; margin-left: 6px; }
  button.act { padding: 5px 12px; border-radius: 6px; border: 1px solid #1f2328; background: #1f2328; color: #fff; cursor: pointer; }
  button.act.alt { background: #fff; color: #1f2328; }
  #status { font-size: 12px; color: #57606a; }
  #wrap { padding: 12px; }
  table { border-collapse: collapse; width: 100%; background: #fff; }
  th, td { border: 1px solid #d8dee4; padding: 6px 8px; vertical-align: top; text-align: left; font-size: 13px; word-break: break-word; }
  th { background: #f6f8fa; cursor: pointer; white-space: nowrap; position: sticky; top: 49px; }
  th .arrow { color: #0969da; }
  td.url a { color: #0969da; text-decoration: none; }
  tr.m-yes { background: #e6ffec; }
  tr.m-later { background: #fff8c5; }
  tr.m-no { background: #f0f0f0; color: #6e7781; }
  .mk { display: inline-flex; gap: 4px; margin-right: 6px; }
  .mk button { border: 1px solid #d0d7de; background: #fff; border-radius: 6px; padding: 2px 7px; cursor: pointer; font-size: 13px; }
  .mk button.on { border-color: #1f2328; box-shadow: 0 0 0 1px #1f2328; }
  .hidden { display: none !important; }
</style>
</head>
<body>
<div id="toolbar">
  <input id="q" type="text" placeholder="搜索仓库…">
  <span id="markfilter"></span>
  <span id="coltoggles"></span>
  <button id="save" class="act">保存标注</button>
  <button id="export" class="act alt">导出关注清单</button>
  <span id="status"></span>
</div>
<div id="wrap">
  <table id="grid">
    <thead><tr id="headrow"></tr></thead>
    <tbody id="body"></tbody>
  </table>
</div>
<script>
const PAYLOAD = __PAYLOAD__;
document.title = "CSV Review — " + PAYLOAD.name;
const COLUMNS = PAYLOAD.columns;
const ROWS = PAYLOAD.rows;
let marks = {};
for (const k in PAYLOAD.marks) if (PAYLOAD.marks[k]) marks[k] = PAYLOAD.marks[k];
let filter = "";
let query = "";
let colOn = {};
COLUMNS.forEach(c => colOn[c] = true);
let sortKey = null, sortDesc = false;

const $ = id => document.getElementById(id);
function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
function markOf(i) { return marks[ROWS[i][0]] || ""; }
function rowMatches(i) {
  const m = markOf(i);
  if (filter === "unmarked" && m) return false;
  if (filter && filter !== "all" && m !== filter) return false;
  if (query) {
    const hay = ROWS[i].map((v, c) => COLUMNS[c] === "url" ? "" : String(v)).join(" ").toLowerCase();
    if (hay.indexOf(query) === -1) return false;
  }
  return true;
}
function compare(i, j) {
  const ci = COLUMNS.indexOf(sortKey);
  const va = ci >= 0 ? ROWS[i][ci] : "";
  const vb = ci >= 0 ? ROWS[j][ci] : "";
  let r;
  if (sortKey === "stargazersCount") r = (parseInt(va, 10) || 0) - (parseInt(vb, 10) || 0);
  else r = String(va).localeCompare(String(vb));
  return sortDesc ? -r : r;
}
function visible() {
  const out = [];
  for (let i = 0; i < ROWS.length; i++) if (rowMatches(i)) out.push(i);
  if (sortKey) out.sort(compare);
  return out;
}
function render() {
  const hr = $("headrow");
  hr.innerHTML = "";
  COLUMNS.forEach(c => {
    const th = document.createElement("th");
    th.className = colOn[c] ? "" : "hidden";
    th.innerHTML = esc(c) + (sortKey === c ? ' <span class="arrow">' + (sortDesc ? "▼" : "▲") + "</span>" : "");
    th.onclick = () => {
      if (sortKey === c) sortDesc = !sortDesc; else { sortKey = c; sortDesc = false; }
      render();
    };
    hr.appendChild(th);
  });
  const tb = $("body");
  tb.innerHTML = "";
  for (const i of visible()) {
    const name = ROWS[i][0];
    const m = markOf(i);
    const tr = document.createElement("tr");
    tr.className = m ? "m-" + m : "";
    COLUMNS.forEach((c, ci) => {
      const td = document.createElement("td");
      td.className = colOn[c] ? "" : "hidden";
      if (c === "url") {
        const a = document.createElement("a");
        a.href = ROWS[i][ci]; a.target = "_blank"; a.rel = "noopener"; a.textContent = ROWS[i][ci];
        td.appendChild(a);
      } else if (c === "fullName") {
        const mk = document.createElement("span");
        mk.className = "mk";
        [["yes", "✅"], ["later", "⏸"], ["no", "❌"]].forEach(([k, sym]) => {
          const b = document.createElement("button");
          b.textContent = sym;
          b.title = { yes: "关注", later: "稍后", no: "跳过" }[k];
          b.className = m === k ? "on" : "";
          b.onclick = ev => {
            ev.stopPropagation();
            marks[name] = (marks[name] === k) ? "" : k;
            render();
          };
          mk.appendChild(b);
        });
        const del = document.createElement("button");
        del.textContent = "✕";
        del.title = "清除标记";
        del.onclick = ev => { ev.stopPropagation(); delete marks[name]; render(); };
        mk.appendChild(del);
        td.appendChild(mk);
        td.appendChild(document.createTextNode(" " + name));
      } else {
        td.textContent = ROWS[i][ci];
      }
      tr.appendChild(td);
    });
    tb.appendChild(tr);
  }
  $("status").textContent = visible().length + " / " + ROWS.length;
}
function buildToolbar() {
  const mf = $("markfilter");
  [["all", "全部"], ["unmarked", "未标"], ["yes", "✅"], ["later", "⏸"], ["no", "❌"]].forEach(([k, lab]) => {
    const c = document.createElement("span");
    c.className = "chip" + (filter === k ? " on" : "");
    c.textContent = lab;
    c.onclick = () => { filter = k; rebuildChips(); render(); };
    mf.appendChild(c);
  });
  const ct = $("coltoggles");
  COLUMNS.forEach(c => {
    const lab = document.createElement("label");
    const cb = document.createElement("input");
    cb.type = "checkbox"; cb.checked = true;
    cb.onchange = () => { colOn[c] = cb.checked; render(); };
    lab.appendChild(cb);
    lab.appendChild(document.createTextNode(" " + c));
    ct.appendChild(lab);
  });
}
function rebuildChips() {
  const order = ["all", "unmarked", "yes", "later", "no"];
  [...$("markfilter").children].forEach((c, i) => c.className = "chip" + (order[i] === filter ? " on" : ""));
}
$("q").addEventListener("input", e => { query = e.target.value.trim().toLowerCase(); render(); });
$("save").onclick = () => {
  const out = {};
  for (const k in marks) if (marks[k]) out[k] = marks[k];
  const st = $("status");
  st.textContent = "保存中…";
  fetch("/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ marks: out }),
  })
    .then(r => r.json())
    .then(d => {
      st.textContent = d.ok
        ? "已保存，更新 " + d.updated + " 行 / 共 " + d.total
        : "保存失败：" + d.error;
    })
    .catch(e => { st.textContent = "保存失败：" + e; });
};
$("export").onclick = () => {
  const lines = [];
  for (const k in marks) {
    if (marks[k] !== "yes") continue;
    const i = ROWS.findIndex(r => r[0] === k);
    if (i < 0) continue;
    const get = c => { const j = COLUMNS.indexOf(c); return j >= 0 ? (ROWS[i][j] || "") : ""; };
    lines.push([k, get("url"), get("description_zh")].join("\t"));
  }
  const text = lines.length ? lines.join("\n") : "（无 ✅ 标记的仓库）";
  const done = () => $("status").textContent = "已复制 " + lines.length + " 条 ✅ 到剪贴板";
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(done, done);
  } else {
    const ta = document.createElement("textarea");
    ta.value = text; document.body.appendChild(ta); ta.select();
    document.execCommand("copy"); ta.remove();
    done();
  }
};
buildToolbar();
render();
</script>
</body>
</html>
"""


def render_html(csv_name, columns, rows, marks):
    keep = [i for i, c in enumerate(columns) if c != "mark"]
    cols = [columns[i] for i in keep]
    rws = [[r[i] for i in keep] for r in rows]
    payload = json.dumps(
        {
            "name": csv_name,
            "columns": cols,
            "rows": rws,
            "marks": {k: v for k, v in marks.items() if v},
        },
        ensure_ascii=False,
    ).replace("</", "<\\/")
    return HTML_TEMPLATE.replace("__PAYLOAD__", payload)


class ReviewHTTPServer(ThreadingHTTPServer):
    daemon_threads = True


class ReviewHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if urlparse(self.path).path == "/":
            self._send(200, "text/html; charset=utf-8", self.server.page.encode("utf-8"))
        else:
            self._send(404, "text/plain; charset=utf-8", b"not found")

    def do_POST(self):
        if urlparse(self.path).path != "/save":
            self._send(404, "application/json", b'{"ok": false}')
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
            marks = payload.get("marks") or {}
            total, updated = apply_marks(self.server.csv_path, marks)
            self._send(200, "application/json",
                       json.dumps({"ok": True, "total": total, "updated": updated}).encode("utf-8"))
        except Exception as e:
            self._send(500, "application/json",
                       json.dumps({"ok": False, "error": str(e)}).encode("utf-8"))

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("csv", help="path to the weekly CSV to review")
    ap.add_argument("--port", type=int, default=8000, help="localhost port (default 8000)")
    ap.add_argument("--no-browser", action="store_true", help="do not auto-open the browser")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.csv):
        raise SystemExit(f"CSV not found: {args.csv}")

    columns, rows = load_csv(args.csv)
    marks = get_marks(columns, rows)
    page = render_html(os.path.basename(args.csv), columns, rows, marks)

    server = ReviewHTTPServer(("127.0.0.1", args.port), ReviewHandler)
    server.csv_path = args.csv
    server.page = page
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"Reviewing {args.csv} ({len(rows)} rows)")
    print(f"Open {url}  —  Ctrl-C to stop")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nBye.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
