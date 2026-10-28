# Timing constraints for ibex_top, for CTS and routing (TP3).
# Same as TP1 and TP2 (period taken from CLOCK_PERIOD in config.json), but
# with propagated clocks (see the end of the file).
create_clock -name clk -period $::env(CLOCK_PERIOD) [get_ports $::env(CLOCK_PORT)]

# Async reset: excluded from timing, as in TP1 and TP2.
set_false_path -from [get_ports rst_ni]

set input_ports [delete_from_list [all_inputs] [get_ports $::env(CLOCK_PORT)]]
set_input_delay  [expr $::env(CLOCK_PERIOD) * 0.2] -clock clk $input_ports
set_output_delay [expr $::env(CLOCK_PERIOD) * 0.2] -clock clk [all_outputs]

# Driving cell and output load come from the selected std cell library.
set driving_cell [split $::env(SYNTH_DRIVING_CELL) "/"]
set_driving_cell -lib_cell [lindex $driving_cell 0] -pin [lindex $driving_cell 1] $input_ports
set_load [expr $::env(OUTPUT_CAP_LOAD) / 1000.0] [all_outputs]

# Same margins as before CTS. Hold uses a smaller one: hold is fixed after
# CTS with buffer insertion, so only basic jitter margin is applied here.
set_clock_uncertainty -setup 0.25 [get_clocks clk]
set_clock_uncertainty -hold  0.10 [get_clocks clk]
set_clock_transition 0.15 [get_clocks clk]

# From CTS on there is a clock tree: compute the real arrival of the clock at
# each flip-flop (latency and skew) through its buffers and wires, instead of
# the ideal clock of TP1 and TP2.
set_propagated_clock [all_clocks]
