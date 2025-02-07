from watertap.flowsheets.MD import MD_single_stage_continuous_recirculation as MD
from idaes.core.util.model_statistics import degrees_of_freedom
import matplotlib.pyplot as plt
import numpy as np
from idaes.core.util.tables import arcs_to_stream_dict, create_stream_table_dataframe
import pandas as pd
import time
from pyomo.environ import units as pyunits, check_optimal_termination, assert_optimal_termination
from watertap.core.util.model_diagnostics import infeasible as infeas

# Original code taken from Nick Tiwari & Chad Able: https://github.com/chad-able/SA2_009_004_EY24/blob/5fe7f72eed2caaf2aa5546309caab3e0070b82ba/examples/md/md.py
# Modifications by Adam Atia on 2/7/2025
# Motivation: determine why increased feed flowrates lead to failure to converge (solves at 1 kg/s, fails at 5 kg/s)
# Takeaway: 

area = 100
def main(vis = False):
    m = MD.build()
    MD.set_operating_conditions(m)

    # Set feed flow rate. Increasing this causes convergence to fail.
    feed_flow_mass = 1 # kg/s
    feed_mass_frac_TDS = 0.035
    m.fs.feed.properties[0].flow_mass_phase_comp["Liq", "TDS"].fix(
        feed_flow_mass * feed_mass_frac_TDS
    )
    feed_mass_frac_H2O = 1 - feed_mass_frac_TDS
    m.fs.feed.properties[0].flow_mass_phase_comp["Liq", "H2O"].fix(
        feed_flow_mass * feed_mass_frac_H2O
    )
    m.fs.MD.area.fix(area)
    
    MD.initialize_system(m)
    res=MD.solve(m)
    assert_optimal_termination(res)
    m.fs.MD.report()

    if vis:
        m.fs.visualize("Flowsheet")
        try:
            print("Type ^C to stop the program")
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("Program stopped")
    
    return m

if __name__ == "__main__":
    m = main()
    feed_mass_frac_TDS = 0.035
    feed_mass_frac_H2O = 1 - feed_mass_frac_TDS

    # Let's see what the cost-optimal length, width, and area would be for increased flowrates.
    MD.optimize_set_up(m)

    # I noticed that area will hit the upper bound of 150m set in the flowsheet. Removing upper bounds.
    m.fs.MD.area.setub(None)
    m.fs.MD.length.setub(None)
    m.fs.MD.width.setub(None)

    # For safe measure--invoking interval initializer before solving
    MD.interval_initializer(m)
    MD.solve(m)
    m.fs.MD.report()

    # Notably, system-level recovery rate of water is set to 50%. I think the 5 kg/s case couldn't solve because more membrane area would be needed to achieve 50% recovery.
    m.fs.overall_recovery.display()

    # Let's loop through mass flowrates, from 2 to 5 kg/s. 5 kg/s can solve now.
    for i in range(2,6):
        feed_flow_mass = i # kg/s
        m.fs.feed.properties[0].flow_mass_phase_comp["Liq", "TDS"].fix(
            feed_flow_mass * feed_mass_frac_TDS
        )
        feed_mass_frac_H2O = 1 - feed_mass_frac_TDS
        m.fs.feed.properties[0].flow_mass_phase_comp["Liq", "H2O"].fix(
            feed_flow_mass * feed_mass_frac_H2O
        )
        res = MD.solve(m, tee=False)
        print(f"FLOWRATE = {i}")


        if check_optimal_termination(res):
            # m.fs.MD.report()
            m.fs.MD.area.display()
        else:
            print("SOLVE FAILED")
            infeas.print_infeasible_constraints(m)