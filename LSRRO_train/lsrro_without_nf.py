from watertap.flowsheets.lsrro import lsrro as lsrro
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
from idaes_ui import fv
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

# class ERDtype(StrEnum):
#     pump_as_turbine = "pump_as_turbine"

solver = get_solver()

def main(vis=False, recovery=0.5, num_stages=5):
    """Build and initialize the LSRRO model"""
    solver = get_solver()

    # Build model
    m, results = lsrro.run_lsrro_case(
        number_of_stages=num_stages,
        water_recovery=recovery,
        Cin=FEED_CONC_MASS_NACL,  # inlet NaCl conc kg/m3,
        Qin=FEED_FLOW_VOL,  # inlet feed flowrate m3/s
        Cbrine=None,  # brine conc kg/m3
        A_case=lsrro.ACase.optimize,
        B_case=lsrro.BCase.optimize,
        AB_tradeoff=lsrro.ABTradeoff.equality_constraint,
        # A_value=4.2e-12, #membrane water permeability coeff m/s-Pa
        has_NaCl_solubility_limit=True,
        has_calculated_concentration_polarization=True,
        has_calculated_ro_pressure_drop=True,
        permeate_quality_limit=2000e-6,
        AB_gamma_factor=1,
        B_max=None,
        number_of_RO_finite_elements=1,
        set_default_bounds_on_module_dimensions=True,
    )


    # Initial solve
    # res = solver.solve(m, tee=False)
    assert_optimal_termination(results)

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
#     """Set up the model for optimization"""
#     solver = get_solver()
    watertap_blocks = []

    for stage in m.fs.NonFinalStages:
        # Add units to costing blocks list

        # watertap_blocks.append(m.fs.Mixers[stage])
        if stage > 1:
            watertap_blocks.append(m.fs.BoosterPumps[stage])

    for stage in m.fs.Stages:
        watertap_blocks.append(m.fs.ROUnits[stage])
        watertap_blocks.append(m.fs.PrimaryPumps[stage])

    for stage in m.fs.EnergyRecoveryDeviceSet:
        watertap_blocks.append(m.fs.EnergyRecoveryDevices[stage])



    return m, watertap_blocks


def setup_costing(m, watertap_blocks):
    """Set up the costing model"""
#     solver = get_solver()

    # Create WaterTAP costing block
    m.fs.costing = WaterTAPCosting()

    # Configure costing for each unit
    for unit in watertap_blocks:
        unit.costing = UnitModelCostingBlock(flowsheet_costing_block=m.fs.costing)

#     # Process costing
#     m.fs.costing.cost_process()
#     m.fs.costing.add_annual_water_production(m.fs.product.properties[0].flow_vol)
#     m.fs.costing.add_LCOW(m.fs.product.properties[0].flow_vol)
#     m.fs.costing.add_specific_energy_consumption(m.fs.product.properties[0].flow_vol)
    m.fs.costing.base_currency = pyunits.USD_2023
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
    if hasattr(m.fs,"objective"):
        del m.fs.objective
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
    # solver = get_solver()
    solve_status = np.zeros(len(recovery_range))
    data = []

    for ind, recovery in enumerate(recovery_range):
        m.fs.water_recovery.fix(recovery)
        print(f"FIXED RECOVERY TO {recovery}")

        res = solver.solve(m, tee=True)
        if check_optimal_termination(res):
            for stage in m.fs.Stages:
                m.fs.ROUnits[stage].area.display()
<<<<<<< variant A
>>>>>>> variant B
            # m.fs.RO.area.display()
======= end

            data_dump = export_variables_to_dict(
                recovery,
                m,
            )

            a_comp = {
                str(stage): value(m.fs.ROUnits[stage].A_comp[0, "H2O"])
                for stage in m.fs.NonFinalStages
            }

            b_comp = {
                str(stage): value(m.fs.ROUnits[stage].B_comp[0, "NaCl"])
                for stage in m.fs.NonFinalStages
            }


            data_dump['A_comp'] = a_comp
            data_dump['B_comp'] = b_comp

            data_dump['number of stages'] = m.fs.NumberOfStages.value
            data.append(data_dump)

            solve_status[ind] = 1
        else:
            print("SOLVE FAILED")
            infeas.print_infeasible_constraints(m)

    dump_to_json(data=data, filename='lsrro_without_nf_6_stage.json')

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
    setup_costing(m, watertap_blocks)
#     breakdown = get_lcow_breakdown(m)
#     breakdown['number of stages'] = m.fs.NumberOfStages.value
#     breakdown['recovery']= m.fs.water_recovery.value
#     dump_to_json(data=[breakdown], filename='lsrro_without_nf_5_stage_lcow_breakdown.json')

    
    m, solve_status = run_recovery_analysis(m, np.arange(0.1, 0.5, 0.02).tolist())
    report_results(m)
