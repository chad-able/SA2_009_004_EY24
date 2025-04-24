from watertap.flowsheets.oaro import oaro_multi as oaro
from idaes.core.util.model_statistics import degrees_of_freedom
import matplotlib.pyplot as plt
import numpy as np
from idaes.core.util.tables import arcs_to_stream_dict, create_stream_table_dataframe
import pandas as pd
import time
from pyomo.environ import units as pyunits, check_optimal_termination, assert_optimal_termination, Objective, Var
from watertap.core.solvers import get_solver
from idaes.core.util.misc import StrEnum
from watertap.core.util.model_diagnostics import infeasible as infeas
from prommis_costing import QGESS_costing


# Original code taken from Nick Tiwari & Chad Able: https://github.com/chad-able/SA2_009_004_EY24/blob/5fe7f72eed2caaf2aa5546309caab3e0070b82ba/examples/oaro/oaro.py
# Modifications by Adam Atia on 2/7/2025
# Motivation: determine why increased feed flowrates lead to failure to converge (solves at 1 kg/s, fails at 5 kg/s)
# Takeaway: Membrane areas should be adjusted with flowrate, and some vars should be unfixed for optimization.

# 4/7/2025: replacing OARO flowsheet with multi-stage OARO flowsheet

class ERDtype(StrEnum):
    pump_as_turbine = "pump_as_turbine"


if __name__ == "__main__":
    solver = get_solver()
    num_stages = 5
    m = oaro.main(number_of_stages=num_stages, system_recovery=0.5, erd_type=ERDtype.pump_as_turbine)
    watertap_blocks2 = []
    # Removing upper bounds on OARO module dimensions, but more importantly, unfixing OARO module area!
    for stage in m.fs.NonFinalStages:
        m.fs.OAROUnits[stage].area.unfix()
        m.fs.OAROUnits[stage].area.setub(None)
        m.fs.OAROUnits[stage].length.setub(None)
        m.fs.OAROUnits[stage].width.setub(None)

        # Unfix OARO feed velocity
        m.fs.OAROUnits[stage].feed_side.velocity[0, 0].unfix()
        watertap_blocks2.append(m.fs.OAROUnits[stage])
        watertap_blocks2.append(m.fs.PrimaryPumps[stage])
        if stage > 1:
            watertap_blocks2.append(m.fs.RecyclePumps[stage])
        watertap_blocks2.append(m.fs.EnergyRecoveryDevices[stage])

    # Removing upper bounds on RO module dimensions, but more importantly, unfixing RO module width!
    m.fs.RO.width.unfix()
    m.fs.RO.area.setub(None)
    m.fs.RO.width.setub(None)
    m.fs.RO.length.setub(None)
    watertap_blocks2.append(m.fs.RO)
    watertap_blocks2.append(m.fs.PrimaryPumps[num_stages-1])
    watertap_blocks2.append(m.fs.EnergyRecoveryDevices[num_stages-1])


    m.fs.feed.flow_mass_phase_comp[0, "Liq", "H2O"].fix(7.2258)
    m.fs.feed.flow_mass_phase_comp[0, "Liq", "NaCl"].fix(0.64491)

    res = solver.solve(m, tee=True)
    assert_optimal_termination(res)

    m.fs.mass_water_recovery.unfix()
    m.fs.water_recovery.fix(0.2)
    res = solver.solve(m, tee=True)
    assert_optimal_termination(res)
    m.fs.water_recovery.fix(0.5)
    m.fs.feed.flow_mass_phase_comp[0, "Liq", "H2O"].unfix()
    m.fs.feed.flow_mass_phase_comp[0, "Liq", "NaCl"].unfix()
    m.fs.feed.properties[0].flow_vol_phase["Liq"].fix(0.014877*1)                # volumetric flow rate (m3/s), equal to 235.8 gpm
    m.fs.feed.properties[0].conc_mass_phase_comp["Liq", "NaCl"].fix(99.304)        # conc in g/L #base 99.304
    res = solver.solve(m, tee=True)
    assert_optimal_termination(res)
    m = QGESS_costing(m=m, units=watertap_blocks2, water_flow_rate=pyunits.convert(m.fs.product.properties[0].flow_vol,
                                                                                   to_units=pyunits.m ** 3 / pyunits.hr))
    m.fs.objective = Objective(expr=m.fs.costing.QGESS_LCOW)
    res = solver.solve(m, tee=True)
    assert_optimal_termination(res)
    m.fs.costing.QGESS_LCOW.display()
    # for v in m.component_objects(Var, descend_into=True):
    #     print("FOUND VAR:" + v.name)
    #     v.pprint()
    # m = main()
    # feed_mass_frac_NaCl = 0.03
    # feed_mass_frac_H2O = 1 - feed_mass_frac_NaCl

    # # Removing upper bounds on OARO module dimensions, but more importantly, unfixing OARO module area!
    # m.fs.OARO.area.unfix()
    # m.fs.OARO.area.setub(None)
    # m.fs.OARO.length.setub(None)
    # m.fs.OARO.width.setub(None)

    # # Unfix OARO feed velocity
    # m.fs.OARO.feed_side.velocity[0,0].unfix()

    # # Removing upper bounds on RO module dimensions, but more importantly, unfixing RO module width!
    # m.fs.RO.width.unfix()
    # m.fs.RO.area.setub(None)
    # m.fs.RO.width.setub(None)
    # m.fs.RO.length.setub(None)

    # feed_flow_mass = 1 # kg/s
    # m.fs.feed.properties[0].flow_mass_phase_comp["Liq", "NaCl"].fix(
    #     feed_flow_mass * feed_mass_frac_NaCl
    # )
    # feed_mass_frac_H2O = 1 - feed_mass_frac_NaCl
    # m.fs.feed.properties[0].flow_mass_phase_comp["Liq", "H2O"].fix(
    #     feed_flow_mass * feed_mass_frac_H2O
    # )
    # res = oaro.solve(m, tee=True)

    # # NF Permeate conditions
    # m.fs.feed.flow_mass_phase_comp[0,"Liq","H2O"].fix(7.2258)
    # m.fs.feed.flow_mass_phase_comp[0,"Liq","NaCl"].fix(0.64491)
    # res = oaro.solve(m, tee=False)
    # assert_optimal_termination(res)
    # Let's loop through mass flowrates, from 2 to 5 kg/s. 5 kg/s can solve now.
    # for i in range(2,6):
    #     feed_flow_mass = i # kg/s
    #     m.fs.feed.properties[0].flow_mass_phase_comp["Liq", "NaCl"].fix(
    #         feed_flow_mass * feed_mass_frac_NaCl
    #     )
    #     feed_mass_frac_H2O = 1 - feed_mass_frac_NaCl
    #     m.fs.feed.properties[0].flow_mass_phase_comp["Liq", "H2O"].fix(
    #         feed_flow_mass * feed_mass_frac_H2O
    #     )
    #     res = oaro.solve(m, tee=True)
    #     print(f"FLOWRATE = {i}")

    #     if check_optimal_termination(res):
    #         oaro.display_system(m)

    #         m.fs.OARO.area.display()
    #         m.fs.RO.area.display()

    #     else:
    #         print("SOLVE FAILED")
    #         infeas.print_infeasible_constraints(m)