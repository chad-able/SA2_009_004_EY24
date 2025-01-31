from watertap.flowsheets.MD import MD_single_stage_continuous_recirculation as MD
from idaes.core.util.model_statistics import degrees_of_freedom
import matplotlib.pyplot as plt
import numpy as np
from idaes.core.util.tables import arcs_to_stream_dict, create_stream_table_dataframe
import pandas as pd
import time
from pyomo.environ import units as pyunits

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

    MD.initialize_system(m)
    m.fs.MD.area.fix(area)
    MD.solve(m)
    m.fs.MD.report()

    if vis:
        m.fs.visualize("Flowsheet")
        try:
            print("Type ^C to stop the program")
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("Program stopped")

if __name__ == "__main__":
    main()


