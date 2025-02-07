from watertap.flowsheets.oaro import oaro
from idaes.core.util.model_statistics import degrees_of_freedom
import matplotlib.pyplot as plt
import numpy as np
from idaes.core.util.tables import arcs_to_stream_dict, create_stream_table_dataframe
import pandas as pd
import time
from pyomo.environ import units as pyunits, check_optimal_termination, assert_optimal_termination
from watertap.core.solvers import get_solver
from idaes.core.util.misc import StrEnum
from watertap.core.util.model_diagnostics import infeasible as infeas


class ERDtype(StrEnum):
    pump_as_turbine = "pump_as_turbine"

def main(erd_type=ERDtype.pump_as_turbine, raise_on_failure=False):
    # set up solver
    solver = get_solver()

    # build, set, and initialize
    m = oaro.build(erd_type=erd_type)
    oaro.set_operating_conditions(m)

    feed_flow_mass = 1 # kg/s
    feed_mass_frac_NaCl = 0.03
    feed_mass_frac_H2O = 1 - feed_mass_frac_NaCl
    m.fs.feed.properties[0].flow_mass_phase_comp["Liq", "NaCl"].fix(
        feed_flow_mass * feed_mass_frac_NaCl
    )
    m.fs.feed.properties[0].flow_mass_phase_comp["Liq", "H2O"].fix(
        feed_flow_mass * feed_mass_frac_H2O
    )

    oaro.initialize_system(m, solver=solver)
    oaro.optimize_set_up(m)
    res = oaro.solve(m, solver=solver)
    assert_optimal_termination(res)

    print("\n***---Optimization results---***")
    oaro.display_system(m)
    if erd_type == ERDtype.pump_as_turbine:
        oaro.display_state(m)
    else:
        pass

    return m

if __name__ == "__main__":
    m = main()
    feed_mass_frac_NaCl = 0.03
    feed_mass_frac_H2O = 1 - feed_mass_frac_NaCl

    # Removing upper bounds on OARO module dimensions, but more importantly, unfixing OARO module area!
    m.fs.OARO.area.unfix()
    m.fs.OARO.area.setub(None)
    m.fs.OARO.length.setub(None)
    m.fs.OARO.width.setub(None)

    # Removing upper bounds on RO module dimensions, but more importantly, unfixing RO module width!
    m.fs.RO.width.unfix()
    m.fs.RO.area.setub(None)
    m.fs.RO.width.setub(None)
    m.fs.RO.length.setub(None)


    # Let's loop through mass flowrates, from 2 to 5 kg/s. 5 kg/s can solve now.
    for i in range(5,6):
        feed_flow_mass = i # kg/s
        m.fs.feed.properties[0].flow_mass_phase_comp["Liq", "NaCl"].fix(
            feed_flow_mass * feed_mass_frac_NaCl
        )
        feed_mass_frac_H2O = 1 - feed_mass_frac_NaCl
        m.fs.feed.properties[0].flow_mass_phase_comp["Liq", "H2O"].fix(
            feed_flow_mass * feed_mass_frac_H2O
        )
        res = oaro.solve(m, tee=True)
        print(f"FLOWRATE = {i}")

        if check_optimal_termination(res):
            oaro.display_system(m)

            m.fs.OARO.area.display()
        else:
            print("SOLVE FAILED")
            infeas.print_infeasible_constraints(m)