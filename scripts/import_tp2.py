#!/usr/bin/env python3
"""Import the placed design of a TP2 run, so CTS and routing start from it.

Usage: import_tp2.py <tp2_design_dir> <design> <run_name>

<tp2_design_dir> is designs/<design> of the TP2 project as seen from the
container (/tp2_design), and <run_name> the name of a placement run in its
runs/ directory (made with `make place` in TP2). Everything is copied to
designs/<design>/tp2/:

    tp2/<design>.odb      placed layout: the input of CTS
    tp2/<design>.def      the same layout, as DEF
    tp2/<design>.nl.v     netlist after placement (with the repair buffers)
    tp2/<design>.pnl.v    the same netlist, with power connections
    tp2/<design>.h.json   JSON header (power pins of the macros)
    tp2/reports/          TP2 reports (qor, placement, timing, ...) to compare with
    tp2/tp1_metrics.json  metrics of the TP1 run (pre-PnR STA), to compare with
    tp2/state.json        initial state for LibreLane (--with-initial-state)
    tp2/SOURCE            which TP2 (and TP1) run this came from
"""
import json
import shutil
import sys
from pathlib import Path

# The STA after detailed placement: the last step of `make place` in TP2.
STA_STEP = "openroad-stamidpnr-1"

# Values the TP3 config assumes; a TP2 run with other values is not comparable.
EXPECTED = {"STD_CELL_LIBRARY": "sky130_fd_sc_hd", "CLOCK_PERIOD": 100}

# Layout and netlist views carried over. The SDC is not: TP2's one keeps the
# clock ideal, and from CTS on it has to be propagated (constraints.sdc).
VIEWS = ("odb", "def", "nl", "pnl", "json_h")


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    tp2, design, name = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]).name
    run = tp2 / "runs" / name

    if not (run / "resolved.json").is_file():
        sys.exit(f"error: {name} is not a LibreLane run directory of TP2 (no resolved.json)")
    states = sorted(run.glob(f"*-{STA_STEP}/state_out.json"))
    if not states:
        sys.exit(f"error: {name} did not finish the placement: use a run made with "
                 f"`make place` in TP2")
    state = json.loads(states[-1].read_text())
    resolved = json.loads((run / "resolved.json").read_text())

    config = json.loads((Path("designs") / design / "config.json").read_text())
    expected = dict(EXPECTED, DESIGN_NAME=config["DESIGN_NAME"])
    for key, want in expected.items():
        if resolved.get(key) != want:
            sys.exit(f"error: {name} has {key} = {resolved.get(key)}, expected {want}. "
                     f"Use a run with the original TP2 configuration.")

    dest = Path("designs") / design / "tp2"
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)

    def localize(path: str) -> str:
        """Copy a file of the TP2 design directory (path inside the TP2
        container, /work/designs/<design>/...) to dest."""
        parts = Path(path).parts
        top = ("designs", design)
        i = next((i for i in range(len(parts) - 1) if parts[i:i + 2] == top), None)
        if i is None:
            sys.exit(f"error: {path} is not inside designs/{design} of TP2")
        src = tp2.joinpath(*parts[i + 2:])
        shutil.copy(src, dest / src.name)
        return f"/work/{dest}/{src.name}"

    new_state = {k: localize(state[k]) for k in VIEWS if state.get(k)}
    new_state["metrics"] = state.get("metrics", {})
    (dest / "state.json").write_text(json.dumps(new_state, indent=2) + "\n")
    if (run / "reports").is_dir():
        shutil.copytree(run / "reports", dest / "reports")

    tp1_state = tp2 / "tp1" / "state.json"
    if tp1_state.is_file():
        metrics = json.loads(tp1_state.read_text()).get("metrics", {})
        (dest / "tp1_metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    tp1_source = tp2 / "tp1" / "SOURCE"
    tp1_run = tp1_source.read_text().strip() if tp1_source.is_file() else "-"
    (dest / "SOURCE").write_text(f"{name}\n{tp1_run}\n")

    print(f"Imported TP2 run {name} (netlist of TP1 run {tp1_run}) into {dest}/")


if __name__ == "__main__":
    main()
