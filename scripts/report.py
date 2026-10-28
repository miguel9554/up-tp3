#!/usr/bin/env python3
"""Generate human-readable Markdown reports for a CTS/routing run.

Usage: report.py <design_dir | run_dir>

Given a design directory, the most recent run under <design_dir>/runs is used.
One file per report is written to <run_dir>/reports/:

    qor.md        summary: cells, clock tree, wirelength, timing at each stage
    cts.md        clock tree: buffers, levels, latency, skew, clock power
    routing.md    global and detailed routing, antennas, fill cells (needs route)
    timing.md     timing at each stage (TP1 -> routed), corners, critical paths
"""
import argparse
import json
import re
import sys
from pathlib import Path

TT = "nom_tt_025C_1v80"
CORNERS = ["nom_ss_100C_1v60", "nom_tt_025C_1v80", "nom_ff_n40C_1v95"]


# ---------------------------------------------------------------- helpers

def find_run(path: Path) -> Path:
    if (path / "resolved.json").exists():
        return path
    runs = sorted((path / "runs").glob("*/resolved.json"), key=lambda p: p.stat().st_mtime)
    if not runs:
        sys.exit(f"error: no runs found under {path}")
    return runs[-1].parent


def step_dir(run: Path, name: str):
    """Return the (last) step directory whose name ends with `name`."""
    dirs = sorted(d for d in run.iterdir() if d.is_dir() and d.name.endswith(name))
    return dirs[-1] if dirs else None


def step_dirs(run: Path, name: str):
    """Every step directory whose name ends with `name` or `name-<n>`."""
    pat = re.compile(rf"^\d+-{re.escape(name)}(-\d+)?$")
    return sorted(d for d in run.iterdir() if d.is_dir() and pat.match(d.name))


def read_log(d) -> str:
    logs = sorted(d.glob("*.log")) if d else []
    return logs[0].read_text() if logs else ""


def step_log(run: Path, name: str) -> str:
    return read_log(step_dir(run, name))


def state_metrics(d):
    f = d / "state_out.json" if d else None
    return json.loads(f.read_text()).get("metrics", {}) if f and f.exists() else {}


def table(headers, rows, align=None):
    """Markdown table with columns padded so every '|' lines up."""
    align = align or ["l"] + ["r"] * (len(headers) - 1)
    cells = [[str(c) for c in headers]] + [["-" if c is None else str(c) for c in r] for r in rows]
    widths = [max(3, *(len(r[i]) for r in cells)) for i in range(len(headers))]

    def line(r):
        return "| " + " | ".join(
            c.rjust(w) if a == "r" else c.ljust(w) for c, w, a in zip(r, widths, align)
        ) + " |"

    sep = "| " + " | ".join(
        "-" * (w - 1) + ":" if a == "r" else ":" + "-" * (w - 1) for w, a in zip(widths, align)
    ) + " |"
    return "\n".join([line(cells[0]), sep] + [line(r) for r in cells[1:]])


def fmt(v, nd=3):
    if isinstance(v, (int, float)):
        return "inf" if v == float("inf") else f"{v:.{nd}f}"
    return str(v) if v is not None else "-"


def code(text):
    return "```\n" + text.rstrip() + "\n```"


def grab(pattern, text, cast=float):
    """First group of `pattern` in `text`, converted with `cast` (None if absent)."""
    m = re.search(pattern, text, re.M)
    return cast(m[1]) if m else None


def grab_all(pattern, text, cast=int):
    return sum(cast(x) for x in re.findall(pattern, text, re.M))


def report_section(text: str, name: str) -> str:
    """Section `name` of an OpenSTA report written with `puts` banners."""
    m = re.search(rf"^{re.escape(name)}\n=+\n(.*?)(?=^=+\n\S|\Z)", text, re.M | re.S)
    return m[1].strip() if m else ""


def corner_block(text: str, corner: str) -> str:
    """The part of a multi-corner report that belongs to `corner`."""
    m = re.search(rf"^=+ {re.escape(corner)} Corner =+\n(.*?)(?=^=+ \S+ Corner =+|\Z)",
                  text, re.M | re.S)
    return m[1] if m else text


def sta_file(d, name):
    """A report of a STA step: mid-PnR STAs write it in the step directory,
    the post-PnR STA in one subdirectory per corner (tt here)."""
    if not d:
        return None
    for f in (d / TT / name, d / name):
        if f.exists():
            return f
    return None


def first_path(text: str):
    """The first (worst) timing path of an OpenSTA report_checks output."""
    m = re.search(r"^Startpoint:.*?slack \((?:MET|VIOLATED)\)", text, re.M | re.S)
    return m[0] if m else None


# ---------------------------------------------------------------- reports

class Run:
    def __init__(self, path: Path):
        self.path = path
        self.cfg = json.loads((path / "resolved.json").read_text())
        mf = path / "final" / "metrics.json"
        self.metrics = json.loads(mf.read_text()) if mf.exists() else {}

        tp2 = path.parent.parent / "tp2"
        self.tp2 = (json.loads((tp2 / "state.json").read_text())["metrics"]
                    if (tp2 / "state.json").exists() else {})
        self.tp1 = (json.loads((tp2 / "tp1_metrics.json").read_text())
                    if (tp2 / "tp1_metrics.json").exists() else {})
        src = (tp2 / "SOURCE").read_text().split() if (tp2 / "SOURCE").exists() else []
        self.tp2_run, self.tp1_run = (src + ["-", "-"])[:2]

        self.cts = step_dir(path, "openroad-cts")
        self.cts_log = read_log(self.cts)
        self.sta = {d.name.split("-", 2)[2]: d for d in step_dirs(path, "openroad-stamidpnr")}
        self.grt = step_dir(path, "openroad-globalrouting")
        self.drt = step_dir(path, "openroad-detailedrouting")
        self.signoff = step_dir(path, "openroad-stapostpnr")

    def m(self, key, corner=None):
        return self.metrics.get(f"{key}__corner:{corner}" if corner else key)

    def header(self, title):
        period = self.cfg.get("CLOCK_PERIOD")
        return "\n".join([
            f"# {title}: `{self.cfg['DESIGN_NAME']}`",
            "",
            table(["Item", "Value"], [
                ["Run", self.path.name],
                ["Placement from TP2 run", self.tp2_run],
                ["Netlist from TP1 run", self.tp1_run],
                ["Std cell library", self.cfg.get("STD_CELL_LIBRARY")],
                ["Clock", f"{self.cfg.get('CLOCK_PORT')} @ {period} ns ({1000 / period:.1f} MHz)"
                 if period else "-"],
            ], ["l", "l"]),
            "",
        ])

    # -- data ---------------------------------------------------------------

    def stages(self):
        """[(label, metrics, step dir)] for every timing analysis, in flow
        order. The step dir is None for TP1 and TP2 (ideal clock)."""
        out = [("TP1: synthesis (no wires)", self.tp1, None),
               ("TP2: placement", self.tp2, None)]
        labels = {"stamidpnr-1": "after CTS",
                  "stamidpnr-2": "after timing repair post-CTS",
                  "stamidpnr-3": "after global routing"}
        for name, d in self.sta.items():
            out.append((labels.get(name, name), state_metrics(d), d))
        if self.signoff:
            out.append(("after detailed routing + RCX", state_metrics(self.signoff), self.signoff))
        return [s for s in out if s[1]]

    def cts_nets(self):
        """[(clock net, sinks, leaf buffers, path depth, avg sink wire length)]."""
        out = []
        for m in re.finditer(r"CTS-0098\] Clock net \"(\S+)\"\n(.*?)(?=CTS-0098|CTS-0124|CTS-0033|\Z)",
                             self.cts_log, re.S):
            body = m[2]
            out.append([m[1], grab(r"Sinks (\d+)", body, int), grab(r"Leaf buffers (\d+)", body, int),
                        grab(r"Path depth (\d+ - \d+)", body, str),
                        fmt(grab(r"Average sink wire length ([\d.]+)", body), 0),
                        grab(r"Dummy loads inserted (\d+)", body, int) or 0])
        return out

    def cts_sinks(self):
        """[(clock net, sinks as found before building the tree)]."""
        return re.findall(r"CTS-001[01]\]\s+Clock net \"(\S+)\"(?: for \w+)? has (\d+) sinks", self.cts_log)

    def cts_cells(self):
        rpt = self.cts / "cts.rpt" if self.cts else None
        text = rpt.read_text() if rpt and rpt.exists() else ""
        text = text.split("%OL_END_REPORT")[0]
        used = re.search(r"Cells used:\n(.*?)(?:Dummys used:|\Z)", text, re.S)
        dummy = re.search(r"Dummys used:\n(.*)", text, re.S)

        def cells(m):
            return re.findall(r"(\S+): (\d+)", m[1]) if m else []
        return {"buffers": grab(r"Total number of Buffers Inserted: (\d+)", text, int),
                "used": cells(used), "dummy": cells(dummy)}

    def latency(self, d):
        """The report_clock_latency section of a STA step (tt corner)."""
        rpt = sta_file(d, "clock.rpt")
        if not rpt:
            return ""
        return report_section(corner_block(rpt.read_text(), TT), "report_clock_latency")

    def latency_range(self, d):
        """(min latency, max latency, skew) of the rising clock edge, as text."""
        m = re.search(r"rise -> rise.*?^([\d.]+)\s+([\d.]+)\s+latency\n\s+([\d.]+)\s+skew",
                      self.latency(d), re.M | re.S)
        return tuple(fmt(float(x)) for x in m.groups()) if m else ("-",) * 3

    def power(self, d):
        """{group: (total W, %)} from a STA step's power report (tt corner)."""
        rpt = sta_file(d, "power.rpt")
        if not rpt:
            return {}
        text = corner_block(rpt.read_text(), TT)
        return {g: (float(t), p) for g, t, p in re.findall(
            r"^(Sequential|Combinational|Clock|Macro|Total)\s+\S+\s+\S+\s+\S+\s+(\S+)\s+(\S+%)", text, re.M)}

    def last_sta(self):
        return self.signoff or (list(self.sta.values())[-1] if self.sta else None)

    def hold_repair(self):
        log = step_log(self.path, "openroad-resizertimingpostcts")
        if not log:
            return None
        return {
            "setup": "no violations" if "No setup violations found" in log else
                     (grab(r"RSZ-\d+\] Inserted (\d+) buffers", log, str) or "see log"),
            "hold": "no violations" if "No hold violations found" in log else
                    f"{grab_all(r'RSZ-0046\] Found (\d+) endpoints with hold violations', log)} endpoints, "
                    f"{grab_all(r'RSZ-0032\] Inserted (\d+) hold buffers', log)} hold buffers",
        }

    # -- individual reports -------------------------------------------------

    def qor(self):
        m = self.m
        rows = [
            ["Std cell instances", m("design__instance__count__stdcell")],
            ["Std cell area (µm²)", fmt(m("design__instance__area__stdcell"))],
            ["Clock-class cells (tree, delay buffers and dummy loads)",
             (m("design__instance__count__class:clock_buffer") or 0)
             + (m("design__instance__count__class:clock_inverter") or 0)],
        ]
        tp2_hpwl = self.tp2.get("route__wirelength__estimated")
        rows.append(["Wirelength, HPWL after TP2 placement (µm)", fmt(tp2_hpwl, 0)])
        if self.grt:
            rows.append(["Wirelength after global routing (µm)",
                         fmt(state_metrics(self.grt).get("global_route__wirelength"), 0)])
        if self.drt:
            rows += [["Wirelength after detailed routing (µm)", fmt(m("route__wirelength"), 0)],
                     ["Vias", m("route__vias")],
                     ["DRC violations after detailed routing", m("route__drc_errors")],
                     ["Antenna violations (nets)", m("antenna__violating__nets")]]
        out = [self.header("QoR report"), table(["Metric", "Value"], rows), "",
               f"## Timing at each stage (corner `{TT}`)", "", self.stage_table()]
        if not self.drt:
            out += ["", "Routing: not run (use `make route`)."]
        return "\n".join(out)

    def stage_table(self):
        rows = []
        for label, mm, d in self.stages():
            def g(k):
                return mm.get(f"{k}__corner:{TT}")
            lat = self.latency_range(d) if d else ("0 (ideal)",) * 3
            rows.append([label, fmt(g("timing__setup__ws")), fmt(g("timing__hold__ws")),
                         g("timing__setup_vio__count"), g("timing__hold_vio__count"),
                         g("design__max_slew_violation__count"),
                         g("design__max_cap_violation__count"), *lat])
        return table(["Stage", "Setup WS (ns)", "Hold WS (ns)", "Setup vio", "Hold vio",
                      "Max slew vio", "Max cap vio", "Clock latency min (ns)",
                      "Clock latency max (ns)", "Clock skew (ns)"], rows)

    def cts_report(self):
        if not self.cts:
            return None
        out = [self.header("Clock tree report"), "## Clock nets found", "",
               "Clock nets as found by CTS before building the tree, and how many"
               " clock pins (sinks) each one drives.", "",
               table(["Clock net", "Sinks"], self.cts_sinks()), "",
               "## Clock tree", "",
               "One tree per clock net. Path depth: clock buffers between the root"
               " and a sink. Dummy loads: cells added only as load, to balance the tree.", "",
               table(["Clock net", "Sinks", "Leaf buffers", "Path depth",
                      "Avg. sink wire length (µm)", "Dummy loads"], self.cts_nets())]
        cells = self.cts_cells()
        delay = grab(r"CTS-0037\] Total number of delay buffers: (\d+)", self.cts_log, int)
        out += ["", table(["Item", "Value"], [
            ["Clock buffers inserted", cells["buffers"]],
            ["Delay buffers (latency balancing)", delay or 0],
        ] + [[f"Cell used: `{c}`", n] for c, n in cells["used"]]
          + [[f"Dummy load: `{c}`", n] for c, n in cells["dummy"]])]

        d = self.sta.get("stamidpnr-1")
        lat = self.latency(d)
        if lat:
            out += ["", f"## Clock latency and skew after CTS (corner `{TT}`)", "",
                    "Network latency: delay of the clock from `clk_i` to each clock pin."
                    " Skew: difference between the latest and earliest one.", "", code(lat)]
        rep = self.hold_repair()
        if rep:
            out += ["", "## Timing repair after CTS", "",
                    table(["Check", "Result"], [["Setup", rep["setup"]], ["Hold", rep["hold"]]])]
        pw = self.power(self.last_sta())
        if pw:
            out += ["", f"## Power (corner `{TT}`, last analysis of the run)", "",
                    table(["Group", "Power (mW)", "Share"],
                          [[g, f"{1000 * w:.3f}", p] for g, (w, p) in pw.items()])]
        return "\n".join(out)

    def grt_tables(self):
        """(resources table, final congestion table) of the global routing log."""
        log = read_log(self.grt)
        res = re.search(r"Routing resources analysis:\n(.*?)\n-+\n(.*?)\n-+", log, re.S)
        cong = re.search(r"Final congestion report:\n(.*?)\n-+\n(.*?)\n-+\n(Total.*?)\n", log, re.S)
        resources = [l.split()[:5] for l in res[2].splitlines()] if res else []
        congestion = []
        if cong:
            for l in cong[2].splitlines() + [cong[3]]:
                f = l.replace("/", " ").split()
                congestion.append(f[:4] + [f[-1]])
        return resources, congestion

    def drt_runs(self):
        """[(violations per iteration, diodes inserted before the run)], one
        per call to the detailed router (the first route, then one per antenna
        repair iteration)."""
        log = read_log(self.drt)
        runs = re.split(r"^\+ detailed_route .*$", log, flags=re.M)[1:]
        diodes = [0] + [grab_all(r"GRT-0015\] Inserted (\d+) diodes", r) for r in runs[:-1]]
        return [([int(x) for x in re.findall(r"Number of violations = (\d+)", r)], dio)
                for r, dio in zip(runs, diodes)]

    def drt_first_violations(self):
        """(layers, [(violation type, counts per layer)]) of the first
        iteration of the first route."""
        log = read_log(self.drt)
        m = re.search(r"Number of violations = \d+\.\nViol/Layer\s+(.*)\n((?:\S.*\n)*?)\[INFO", log)
        if not m:
            return [], []
        layers = m[1].split()
        rows = []
        for line in m[2].splitlines():
            f = line.split()
            n = len(layers)
            rows.append([" ".join(f[:-n])] + f[-n:])
        return layers, rows

    def drt_layers(self):
        """({layer: wirelength µm}, {layer: up-vias}) of the final route."""
        log = read_log(self.drt)
        last = log.split("Complete detail routing.")[-1]
        wl = dict(re.findall(r"Total wire length on LAYER (\S+) = (\d+) um", last))
        vias = re.search(r"Up-via summary.*?\n-+\n(.*?)\n-+", last, re.S)
        up = dict(re.findall(r"^\s*(\S+)\s+(\d+)$", vias[1], re.M)) if vias else {}
        up.pop("FR_MASTERSLICE", None)
        return wl, up

    def antenna_summary(self, d):
        rpt = d / "reports" / "antenna_summary.rpt" if d else None
        if not (rpt and rpt.exists()):
            return []
        rows = [[c.strip() for c in l.strip("│ ").split("│")]
                for l in rpt.read_text().splitlines() if l.startswith("│")]
        return rows

    def routing(self):
        if not self.grt:
            return None
        resources, congestion = self.grt_tables()
        grt_log = read_log(self.grt)
        grt = state_metrics(self.grt)
        out = [self.header("Routing report"), "## Global routing", "",
               "Global adjustment (fraction of the tracks reserved for the detailed router): "
               f"{grab(r'Global adjustment: (\S+)', grt_log, str) or '-'}.", "",
               "Routing resources (tracks available in all the gcells, per layer):", "",
               table(["Layer", "Direction", "Original", "Derated", "Reduction"], resources),
               "", "Final congestion (demand: tracks used by the routed nets):", "",
               table(["Layer", "Resource", "Demand", "Usage", "Overflow"], congestion), "",
               table(["Item", "Value"], [
                   ["HPWL after CTS (µm)", fmt(grt.get("route__wirelength__estimated"), 0)],
                   ["Global routing wirelength (µm)", fmt(grt.get("global_route__wirelength"), 0)],
                   ["Routed nets", grab(r"GRT-0014\] Routed nets: (\d+)", grt_log, int)],
                   ["Clock nets", grab(r"GRT-0019\] Found (\d+) clock nets", grt_log, int)],
               ])]

        ant = state_metrics(step_dir(self.path, "openroad-checkantennas"))
        rep_dir = step_dir(self.path, "openroad-repairantennas")
        rep_log = "".join(read_log(d) for d in sorted(rep_dir.glob("*-openroad-diodeinsertion"))) \
            if rep_dir else ""
        rounds = re.findall(r"GRT-0012\] Found (\d+) antenna violations\.\n"
                            r"(?:.*\n)*?.*?(?:GRT-0302\] Inserted (\d+) jumpers|GRT-0015\] Inserted (\d+) diodes)",
                            rep_log)
        out += ["", "## Antennas after global routing", "",
                table(["Item", "Value"], [
                    ["Nets with antenna violations (check after global routing)",
                     ant.get("antenna__violating__nets")],
                    ["Pins with antenna violations", ant.get("antenna__violating__pins")],
                ])]
        if rounds:
            out += ["", "Repair, in steps: each one checks the antennas again and fixes what it"
                    " can, alternately with jumpers (changing layer) and with diodes:", "",
                    table(["Step", "Violations found", "Jumpers inserted", "Diodes inserted"],
                          [[i + 1, v, j or "-", d or "-"] for i, (v, j, d) in enumerate(rounds)])]

        if not self.drt:
            return "\n".join(out)
        m = self.m
        out += ["", "## Detailed routing", "",
                "The router repeats optimization iterations until there are no DRC violations"
                " left. After each complete route, LibreLane checks the antennas again; if"
                " there are violations it adds diodes and routes again.", ""]
        runs = self.drt_runs()
        n = max((len(v) for v, _ in runs), default=0)
        out.append(table(["Route", "Diodes added before"] + [f"Iter {i}" for i in range(n)],
                         [[i, d] + v + [""] * (n - len(v)) for i, (v, d) in enumerate(runs)]))
        layers, viol = self.drt_first_violations()
        if viol:
            out += ["", "Violations after the first iteration of the first route, by type and layer"
                    " (`mcon`, `via`, ...: the vias between layers):", "",
                    table(["Type"] + layers, viol)]
        wl, up = self.drt_layers()
        layers = sorted(set(wl) | set(up), key=lambda x: (x != "li1", x))
        out += ["", "Final wirelength and vias, per layer (up-vias: vias from this layer to the"
                " one above):", "",
                table(["Layer", "Wirelength (µm)", "Up-vias"],
                      [[l, wl.get(l, "-"), up.get(l, "-")] for l in layers]
                      + [["Total", fmt(m("route__wirelength"), 0), m("route__vias")]])]

        fill = step_log(self.path, "openroad-fillinsertion")
        wl_csv = step_dir(self.path, "odb-reportwirelength")
        longest = []
        if wl_csv and (wl_csv / "wire_lengths.csv").exists():
            longest = (wl_csv / "wire_lengths.csv").read_text().splitlines()[1:6]
        disc = step_log(self.path, "odb-reportdisconnectedpins")
        out += ["", "## Checks after detailed routing", "",
                table(["Item", "Value"], [
                    ["DRC violations (detailed router)", m("route__drc_errors")],
                    ["Nets with antenna violations", m("antenna__violating__nets")],
                    ["Antenna diodes (total)", m("design__instance__count__class:antenna_cell")],
                    ["Disconnected pins", grab(r"Found (\d+) disconnected pin", disc, int)],
                    ["Critical disconnected pins",
                     grab(r"disconnected pin\(s\), of which (\d+) are critical", disc, int)],
                    ["Longest net (µm)", fmt(m("route__wirelength__max"), 0)],
                    ["Filler instances inserted",
                     grab(r"DPL-0001\] Placed (\d+) filler instances", fill, int)],
                ])]
        left = self.antenna_summary(step_dir(self.path, "openroad-checkantennas-1"))
        if left:
            out += ["", "Antenna violations left (P / R: ratio found / ratio allowed):", "",
                    table(["P / R", "Partial", "Required", "Net", "Pin", "Layer"], left,
                          ["r", "r", "r", "l", "l", "l"])]
        if longest:
            out += ["", "Longest nets:", "",
                    table(["Net", "Length"], [l.replace("\\", "").rsplit(",", 1) for l in longest],
                          ["l", "r"])]
        return "\n".join(out)

    def timing(self):
        out = [self.header("Timing report"),
               f"## Timing at each stage (corner `{TT}`)", "",
               "TP1 and TP2: ideal clock (no clock tree). From CTS on: propagated clock."
               " Until global routing the wires are estimated; after detailed routing their"
               " resistance and capacitance are extracted from the layout (RCX).", "",
               self.stage_table()]
        last = self.last_sta()
        if self.signoff:
            mm = state_metrics(self.signoff)
            rows = [[c, fmt(mm.get(f"timing__setup__ws__corner:{c}")),
                     fmt(mm.get(f"timing__hold__ws__corner:{c}")),
                     mm.get(f"timing__setup_vio__count__corner:{c}"),
                     mm.get(f"timing__hold_vio__count__corner:{c}"),
                     mm.get(f"design__max_slew_violation__count__corner:{c}"),
                     mm.get(f"design__max_cap_violation__count__corner:{c}")] for c in CORNERS]
            out += ["", "## Corners, after detailed routing", "",
                    "`ss`: slow transistors, 1.60 V, 100 °C. `tt`: typical, 1.80 V, 25 °C."
                    " `ff`: fast, 1.95 V, −40 °C.", "",
                    table(["Corner", "Setup WS (ns)", "Hold WS (ns)", "Setup vio", "Hold vio",
                           "Max slew vio", "Max cap vio"], rows)]
        if last:
            for kind, rpt in (("setup", "max.rpt"), ("hold", "min.rpt")):
                f = sta_file(last, rpt)
                if f:
                    p = first_path(corner_block(f.read_text(), TT))
                    if p:
                        out += ["", f"## Critical {kind} path (corner `{TT}`, {last.name})", "", code(p)]
        return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("path", type=Path, help="design directory or run directory")
    args = ap.parse_args()

    run = Run(find_run(args.path))
    outdir = run.path / "reports"
    outdir.mkdir(exist_ok=True)

    for name, fn in (("qor", run.qor), ("cts", run.cts_report),
                     ("routing", run.routing), ("timing", run.timing)):
        text = fn()
        dest = outdir / f"{name}.md"
        if text is None:
            dest.unlink(missing_ok=True)
            continue
        dest.write_text(text + "\n")
        print(f"wrote {dest}")

    print()
    print((outdir / "qor.md").read_text())


if __name__ == "__main__":
    main()
