# LibreLane clock tree synthesis (CTS) and routing flows, executed inside the
# container via run.sh. They start from the design placed in TP2: nothing here
# runs synthesis, floorplan or placement again. Every run also generates
# reports in <run>/reports/*.md.
#
#   make import-tp2 TP2_RUN=<dir>      # import the placed design of a TP2 run (its directory)
#   make cts                           # CTS + timing repair after CTS + STA
#   make route                         # CTS + global and detailed routing + extraction + STA
#   make route NAME=ref                # same, run tagged rt_ref_<timestamp>
#   make gui                           # open the latest run in the OpenROAD GUI
#   make gui RUN=<run> STEP=05         # open a given run, as it was after a given step
#   make report                        # (re)generate reports of the latest run
#   make shell                         # interactive shell in the container
#   make clean                         # remove runs of DESIGN

DESIGN ?= ibex
TP2_RUN ?=
NAME   ?=
RUN    ?=
STEP   ?=

DESIGN_DIR := designs/$(DESIGN)
CONFIG     := $(DESIGN_DIR)/config.json
STATE      := $(DESIGN_DIR)/tp2/state.json
STAMP      := $(shell date +%Y-%m-%d_%H-%M-%S)
RUNSH      := ./run.sh

LAST_RUN = $(notdir $(patsubst %/resolved.json,%,$(lastword \
             $(shell ls -1tr $(DESIGN_DIR)/runs/*/resolved.json 2>/dev/null))))
GUI_RUN  = $(or $(RUN),$(LAST_RUN))

# $(call FLOW,<tag prefix>,<last step>)
TAG  = $(1)$(if $(NAME),_$(NAME))_$(STAMP)
FLOW = $(RUNSH) librelane --design-dir $(DESIGN_DIR) --run-tag $(TAG) \
         --with-initial-state $(STATE) --from OpenROAD.CTS --to $(2) $(CONFIG) && \
       $(RUNSH) python3 scripts/report.py $(DESIGN_DIR)/runs/$(TAG)

.PHONY: import-tp2 cts route gui report shell clean

# TP2_RUN is <TP2 project>/designs/<design>/runs/<run>: the whole
# designs/<design> of TP2 is mounted, since the run refers to files outside it
# (the TP1 netlist header).
import-tp2:
	@[ -n "$(TP2_RUN)" ] || { echo "error: give the TP2 run directory: make import-tp2 TP2_RUN=<dir>"; exit 1; }
	@[ -d "$(TP2_RUN)" ] || { echo "error: $(TP2_RUN) does not exist"; exit 1; }
	TP2_DESIGN=$(abspath $(TP2_RUN)/../..) $(RUNSH) python3 scripts/import_tp2.py \
	  /tp2_design $(DESIGN) $(notdir $(abspath $(TP2_RUN)))

$(STATE):
	@echo "error: the TP2 placement was not imported yet. Run: make import-tp2 TP2_RUN=<TP2 run dir>"
	@exit 1

cts: $(STATE)
	$(call FLOW,cts,OpenROAD.STAMidPNR-2)

route: $(STATE)
	$(call FLOW,rt,OpenROAD.STAPostPNR)

# Checks there is a display and lets the container (same uid) use it through
# the X11 socket. With GUI_DISPLAY (X server over TCP, see
# docs/gui_windows_mac.md) the X server is authorized by hand instead.
ifeq ($(GUI_DISPLAY),)
define X11
	@[ -n "$$DISPLAY" ] || { echo "error: DISPLAY is not set: run this from a graphical session"; exit 1; }
	@xhost +SI:localuser:$$(id -un) >/dev/null 2>&1 || \
	  echo "warning: xhost failed; if the GUI does not open, install x11-xserver-utils"
endef
else
define X11
	@echo "Using the X server at GUI_DISPLAY=$(GUI_DISPLAY)"
endef
endif

gui:
	@[ -n "$(GUI_RUN)" ] || { echo "error: no runs yet: run make cts or make route"; exit 1; }
	$(X11)
	$(RUNSH) librelane --design-dir $(DESIGN_DIR) --run-tag $(GUI_RUN) --flow OpenInOpenROAD \
	  $(if $(STEP),--with-initial-state $(firstword $(wildcard $(DESIGN_DIR)/runs/$(GUI_RUN)/$(STEP)-*/state_out.json))) \
	  $(CONFIG)

report:
	$(RUNSH) python3 scripts/report.py $(DESIGN_DIR)

shell:
	$(RUNSH)

clean:
	rm -rf $(DESIGN_DIR)/runs
