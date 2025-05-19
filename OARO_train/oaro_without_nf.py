from watertap.flowsheets.oaro import oaro_multi as oaro
from idaes.core.util.model_statistics import degrees_of_freedom
import matplotlib.pyplot as plt
import numpy as np
from idaes.core.util.tables import arcs_to_stream_dict, create_stream_table_dataframe
import pandas as pd
import time
import os
from pyomo.environ import (
    units as pyunits,
    check_optimal_termination,
    assert_optimal_termination,
    Objective,
    Var,
    Expression,
    value
)
from watertap.core.solvers import get_solver
from idaes.core.util.misc import StrEnum
from watertap.core.util.model_diagnostics import infeasible as infeas
from idaes.core import UnitModelCostingBlock
from watertap.costing import WaterTAPCosting

# Get the directory of the current script for relative paths
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, '../'))  # One directory up

# Add project root to path for local imports
import sys
sys.path.append(PROJECT_ROOT)
from prommis_costing import QGESS_costing, get_lcow_breakdown
from MD_Train.helpers import export_variables_to_dict, dump_to_json

# Constants
FEED_FLOW_VOL = 0.014877  # m³/s, equal to 235.8 gpm
FEED_CONC_MASS_NACL = 99.304  # g/L

class ERDtype(StrEnum):
    pump_as_turbine = "pump_as_turbine"


def main(vis=False, recovery=0.5, num_stages=5):
    """Build and initialize the OARO model"""
    solver = get_solver()

    # Build model
    m = oaro.main(
        number_of_stages=num_stages,
        system_recovery=0.5,
        erd_type=ERDtype.pump_as_turbine
    )

    # Initial solve
    res = solver.solve(m, tee=False)
    assert_optimal_termination(res)

    if vis:
        m.fs.visualize("Flowsheet")
        try:
            print("Type ^C to stop the program")
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("Program stopped")

    return m, num_stages


def setup_optimization(m, num_stages):
    """Set up the model for optimization"""
    solver = get_solver()
    watertap_blocks = []

    # Removing upper bounds on OARO module dimensions, unfixing OARO module area
    for stage in m.fs.NonFinalStages:
        m.fs.OAROUnits[stage].area.unfix()
        m.fs.OAROUnits[stage].area.setub(None)
        m.fs.OAROUnits[stage].length.setub(None)
        m.fs.OAROUnits[stage].width.setub(None)

        # Unfix OARO feed velocity
        m.fs.OAROUnits[stage].feed_side.velocity[0, 0].unfix()

        # Add units to costing blocks list
        watertap_blocks.append(m.fs.OAROUnits[stage])
        watertap_blocks.append(m.fs.PrimaryPumps[stage])

        if stage > 1:
            watertap_blocks.append(m.fs.RecyclePumps[stage])

        watertap_blocks.append(m.fs.EnergyRecoveryDevices[stage])

    # Removing upper bounds on RO module dimensions, unfixing RO module width
    m.fs.RO.width.unfix()
    m.fs.RO.area.setub(None)
    m.fs.RO.width.setub(None)
    m.fs.RO.length.setub(None)

    # Add RO and final stage components to costing blocks list
    watertap_blocks.append(m.fs.RO)
    watertap_blocks.append(m.fs.PrimaryPumps[num_stages-1])
    watertap_blocks.append(m.fs.EnergyRecoveryDevices[num_stages-1])

    # Fix initial flow conditions
    m.fs.feed.flow_mass_phase_comp[0, "Liq", "H2O"].fix(7.2258)
    m.fs.feed.flow_mass_phase_comp[0, "Liq", "NaCl"].fix(0.64491)

    # Solve with initial conditions
    res = solver.solve(m, tee=False)
    assert_optimal_termination(res)

    # Update recovery and release mass flow constraints
    m.fs.mass_water_recovery.unfix()
    m.fs.water_recovery.fix(0.2)

    # Solve with new recovery
    res = solver.solve(m, tee=False)
    assert_optimal_termination(res)

    # Update feed conditions
    m.fs.feed.flow_mass_phase_comp[0, "Liq", "H2O"].unfix()
    m.fs.feed.flow_mass_phase_comp[0, "Liq", "NaCl"].unfix()
    m.fs.feed.properties[0].flow_vol_phase["Liq"].fix(FEED_FLOW_VOL)  # m3/s, equal to 235.8 gpm
    m.fs.feed.properties[0].conc_mass_phase_comp["Liq", "NaCl"].fix(FEED_CONC_MASS_NACL)  # g/L

    # Solve with updated feed conditions
    res = solver.solve(m, tee=False)
    if check_optimal_termination(res):
        print("Optimization setup successful")
    else:
        print("SOLVE FAILED")
        infeas.print_infeasible_constraints(m)

    return m, watertap_blocks


def setup_costing(m, watertap_blocks):
    """Set up the costing model"""
    solver = get_solver()

    # Create WaterTAP costing block
    m.fs.costing = WaterTAPCosting()

    # Configure costing for each unit
    for unit in watertap_blocks:
        unit.costing = UnitModelCostingBlock(flowsheet_costing_block=m.fs.costing)

    # Process costing
    m.fs.costing.cost_process()
    m.fs.costing.add_annual_water_production(m.fs.product.properties[0].flow_vol)
    m.fs.costing.add_LCOW(m.fs.product.properties[0].flow_vol)
    m.fs.costing.add_specific_energy_consumption(m.fs.product.properties[0].flow_vol)
    m.fs.costing.base_currency = pyunits.USD_2018
    cost_params = {
        'has_liquid_waste': True
    }
    # Create QGESS costing
    m = QGESS_costing(
        m=m,
        units=watertap_blocks,
        water_flow_rate=pyunits.convert(
            m.fs.product.properties[0].flow_vol,
            to_units=pyunits.m**3 / pyunits.hr
        ),
        liq_waste=m.fs.disposal.properties[0].flow_vol,
        **cost_params
    )

    # Set objective function
    m.fs.objective = Objective(expr=m.fs.costing.QGESS_LCOW)

    # Solve with costing
    res = solver.solve(m, tee=False)
    if check_optimal_termination(res):
        print("Costing setup successful")
    else:
        print("SOLVE FAILED")
        infeas.print_infeasible_constraints(m)

    return m


def run_recovery_analysis(m, recovery_range=(0.5,)):
    """Run analysis for different recovery values"""
    solver = get_solver()
    solve_status = np.zeros(len(recovery_range))
    data = []

    for ind, recovery in enumerate(recovery_range):
        m.fs.water_recovery.fix(recovery)
        print(f"FIXED RECOVERY TO {recovery}")

        res = solver.solve(m, tee=True)
        if check_optimal_termination(res):
            for stage in m.fs.NonFinalStages:
                m.fs.OAROUnits[stage].area.display()
            m.fs.RO.area.display()

            data_dump = export_variables_to_dict(
                recovery,
                m.fs.costing,
            )

            data_dump['number of stages'] = m.fs.NumberOfStages.value
            data.append(data_dump)

            solve_status[ind] = 1
        else:
            print("SOLVE FAILED")
            infeas.print_infeasible_constraints(m)

    dump_to_json(data=data, filename='oaro_without_nf_5_stage.json')

    print(f"solve status:\n{solve_status}")
    return m, solve_status


def report_results(m):
    """Report final results"""
    solver = get_solver()
    res = solver.solve(m, tee=False)
    assert_optimal_termination(res)

    m.fs.costing.QGESS_LCOW.display()
    print(f"Electricity cost: {value(m.fs.costing.aggregate_flow_costs['electricity'])}")

    # Additional reporting could be added here

    return m


if __name__ == "__main__":
    # Main execution flow
    m, num_stages = main(num_stages=5, vis=False, recovery=0.5)
    m, watertap_blocks = setup_optimization(m, num_stages)
    m = setup_costing(m, watertap_blocks)
    breakdown = get_lcow_breakdown(m)
    breakdown['number of stages'] = m.fs.NumberOfStages.value
    breakdown['recovery']= m.fs.water_recovery.value
    dump_to_json(data=[breakdown], filename='oaro_without_nf_5_stage_lcow_breakdown.json')

    
#    m, solve_status = run_recovery_analysis(m, np.arange(0.1, 0.5, 0.02).tolist())
    m = report_results(m)
