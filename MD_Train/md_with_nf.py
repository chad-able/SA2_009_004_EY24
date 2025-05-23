import os
import json
import time
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pyomo.environ import (
    Expression,
    Objective,
    units as pyunits,
    check_optimal_termination,
    assert_optimal_termination,
    value,
    Var
)
from helpers import export_variables_to_dict, dump_to_json

# IDAES and WaterTAP imports
from base_flowsheets import MD_single_stage_recirc_no_costing as MD
from idaes.core import UnitModelCostingBlock
from idaes.core.util.model_statistics import degrees_of_freedom
from idaes.core.util.tables import arcs_to_stream_dict, create_stream_table_dataframe
from watertap.core.util.model_diagnostics import infeasible as infeas
from watertap.costing import WaterTAPCosting
from watertap.costing.unit_models.heater_chiller import cost_heater_chiller
import watertap.property_models.multicomp_aq_sol_prop_pack as props
from watertap.unit_models.nanofiltration_ZO import NanofiltrationZO
from watertap.unit_models.pressure_changer import Pump

# Get the directory of the current script for relative paths
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, '..'))  # Two directories up

# Add project root to path for local imports
import sys
sys.path.append(PROJECT_ROOT)
from prommis_costing import QGESS_costing, get_lcow_breakdown

# Constants
MEMBRANE_AREA = 100  # m²
FEED_FLOW_MASS = 1  # kg/s
FEED_MASS_FRAC_TDS = 0.035
CONC_MASS_COMP_TDS = 86.65 #g/L
NF_RECOVERY = 0.5


def load_solute_data():
    """Load solute parameters from JSON file"""
    json_path = os.path.join(PROJECT_ROOT, 'solute_parameters.json')
    with open(json_path) as f:
        return json.load(f)


def main(vis=False):
    """Build and initialize the MD model"""
    m = MD.build()
    MD.set_operating_conditions(m)

    # Set feed flow rate
    feed_mass_frac_H2O = 1 - FEED_MASS_FRAC_TDS
    m.fs.feed.properties[0].flow_mass_phase_comp["Liq", "TDS"].fix(
        FEED_FLOW_MASS * FEED_MASS_FRAC_TDS
    )
    m.fs.feed.properties[0].flow_mass_phase_comp["Liq", "H2O"].fix(
        FEED_FLOW_MASS * feed_mass_frac_H2O
    )

    # Fix membrane area
    m.fs.MD.area.fix(MEMBRANE_AREA)

    # Initialize and solve
    MD.initialize_system(m)
    res = MD.solve(m)
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


def setup_optimization(m):
    """Set up the model for optimization"""
    # Prepare for optimization
    MD.optimize_set_up(m)

    # Remove upper bounds
    m.fs.MD.area.setub(None)
    m.fs.MD.length.setub(None)
    m.fs.MD.width.setub(None)

    # Initialize and solve
    MD.interval_initializer(m)
    MD.solve(m)
    m.fs.MD.report()
    m.fs.overall_recovery.display()

    # Update feed conditions
    m.fs.feed.flow_mass_phase_comp[0, "Liq", "H2O"].unfix()
    m.fs.feed.flow_mass_phase_comp[0, "Liq", "TDS"].unfix()
    m.fs.feed.properties[0].flow_vol_phase["Liq"].fix(0.014877 * NF_RECOVERY)
    # m3/s, equal to 235.8 gpm/2 post NF
    m.fs.feed.properties[0].conc_mass_phase_comp["Liq", "TDS"].fix(CONC_MASS_COMP_TDS)
    # g/L post NF at 50%

   # Set 2000ppm TDS limit for product water
    m.fs.permeate.properties[0].mass_frac_phase_comp["Liq", "TDS"].setub(2000e-6)    # Solve with updated feed conditions
 
    # Solve with new feed conditions
    res = MD.solve(m, tee=False)
    if check_optimal_termination(res):
        m.fs.MD.area.display()
    else:
        print("SOLVE FAILED")
        infeas.print_infeasible_constraints(m)

    return m


def setup_nf_for_costing(m):
    """Set up the NF system for costing"""
    # Load solute data
    solute_data = load_solute_data()

    # Prepare solute properties
    solute_list = list(solute_data.keys())
    mw_data = {key: solute_data[key]['mw'] for key in solute_list}
    charge = {key: solute_data[key]['charge'] for key in solute_list}
    diffusivity = {("Liq", key): 1e-9 for key in solute_list}

    # Set up property package
    m.fs.properties = props.MCASParameterBlock(
        solute_list=solute_list,
        mw_data=mw_data,
        charge=charge,
        diffusivity_data=diffusivity,
        density_calculation=props.DensityCalculation.seawater,
        material_flow_basis=props.MaterialFlowBasis.mass
    )

    # Create NF and pump units
    m.fs.nf = NanofiltrationZO(property_package=m.fs.properties)
    m.fs.P1 = Pump(property_package=m.fs.properties)

    # Configure pump
    m.fs.P1.efficiency_pump.fix(0.80)  # pump efficiency [-]
    m.fs.P1.outlet.pressure[0].fix(10e5)

    # Configure NF
    m.fs.nf.properties_permeate[0].pressure.fix(101325)
    m.fs.nf.recovery_vol_phase.fix(0.5)
    m.fs.nf.flux_vol_solvent.fix(1.446759259259259e-5)
    m.fs.nf.area.fix(499.44685)

    return m


def setup_costing(m):
    """Set up the costing model"""
    # Create WaterTAP costing block
    m.fs.costing = WaterTAPCosting()

    # Units to include in costing
    watertap_blocks = [
        m.fs.MD,
        m.fs.nf,
        m.fs.P1,
        m.fs.hx,
        m.fs.heater,
        m.fs.chiller,
        m.fs.mixer,
        m.fs.pump_feed,
        m.fs.pump_brine,
        m.fs.pump_permeate
    ]

    # Configure costing for each unit
    for unit in watertap_blocks:
        if unit == m.fs.chiller:
            unit.costing = UnitModelCostingBlock(
                flowsheet_costing_block=m.fs.costing,
                costing_method=cost_heater_chiller,
                costing_method_arguments={"HC_type": "chiller"},
            )
        elif unit == m.fs.heater:
            unit.costing = UnitModelCostingBlock(
                flowsheet_costing_block=m.fs.costing,
                costing_method=cost_heater_chiller,
                costing_method_arguments={"HC_type": "electric_heater"},
            )
        else:
            unit.costing = UnitModelCostingBlock(flowsheet_costing_block=m.fs.costing)

    # Process costing
    m.fs.costing.cost_process()
    m.fs.costing.add_annual_water_production(m.fs.permeate.properties[0].flow_vol)
    m.fs.costing.add_LCOW(m.fs.permeate.properties[0].flow_vol)
    m.fs.costing.add_specific_energy_consumption(m.fs.permeate.properties[0].flow_vol)
    m.fs.costing.base_currency = pyunits.USD_2018
    cost_params = {
        'has_liquid_waste': True
    }
    liquid_waste = m.fs.reject.properties[0].flow_vol + m.fs.feed.properties[0].flow_vol * NF_RECOVERY / (1 - NF_RECOVERY)
    # Apply QGESS costing
    m = QGESS_costing(
        m=m,
        units=watertap_blocks,
        water_flow_rate=pyunits.convert(
            m.fs.permeate.properties[0].flow_vol,
            to_units=pyunits.m**3 / pyunits.hr
        ),
        liq_waste=liquid_waste,
        **cost_params
    )

    # Set objective function
    m.fs.objective = Objective(expr=m.fs.costing.QGESS_LCOW)

    return m


def run_recovery_analysis(m, recovery_range=(0.5,)):
    """Run analysis for different recovery values"""
    solve_status = np.zeros(len(recovery_range))

    data = []

    for ind, recovery in enumerate(recovery_range):
        m.fs.overall_recovery.fix(recovery)
        print(f"FIXED RECOVERY TO {recovery}")

        res = MD.solve(m, tee=True)
        if check_optimal_termination(res):
            m.fs.MD.area.display()

            data.append(export_variables_to_dict(recovery,
                                                 m,
                                                 nf_recovery_fraction=NF_RECOVERY,
                                                 ))

            solve_status[ind] = 1
        else:
            print("SOLVE FAILED")
            infeas.print_infeasible_constraints(m)

    dump_to_json(data=data,
                 filename=f'md_with_nf_{NF_RECOVERY}_recovery.json')

    print(f"solve status:\n{solve_status}")
    return m, solve_status

def report_results(m):
    """Report final results"""
    assert_optimal_termination(MD.solve(m))
    m.fs.nf.area.display()
    m.fs.costing.QGESS_LCOW.display()

def get_breakdown(m):
    m, solve_status = run_recovery_analysis(m)
    breakdown = get_lcow_breakdown(m)
    breakdown['recovery']= m.fs.overall_recovery.value
    dump_to_json(data=[breakdown], filename='md_with_nf_lcow_breakdown.json')
    return m, breakdown

if __name__ == "__main__":
    # Main execution flow
    m = main()
    m = setup_optimization(m)
    m = setup_nf_for_costing(m)
    m = setup_costing(m)
#    m, solve_status = run_recovery_analysis(m,(np.arange(0.2,0.6,0.02)*1.3).tolist())
    m, breakdown = get_breakdown(m)

    report_results(m)


