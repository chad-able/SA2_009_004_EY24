# from watertap.flowsheets.MD import MD_single_stage_continuous_recirculation as MD
import MD_single_stage_recirc_no_costing as MD
from idaes.core.util.model_statistics import degrees_of_freedom
import matplotlib.pyplot as plt
import numpy as np
from idaes.core.util.tables import arcs_to_stream_dict, create_stream_table_dataframe
import pandas as pd
import time
from pyomo.environ import Expression,Objective,units as pyunits, check_optimal_termination, assert_optimal_termination, value
from watertap.core.util.model_diagnostics import infeasible as infeas
from prommis_costing import QGESS_costing
from watertap.costing.unit_models.heater_chiller import (
    cost_heater_chiller,
)
from watertap.costing import WaterTAPCosting
from idaes.core import UnitModelCostingBlock
from pyomo.util.check_units import assert_units_consistent
# Original code taken from Nick Tiwari & Chad Able: https://github.com/chad-able/SA2_009_004_EY24/blob/5fe7f72eed2caaf2aa5546309caab3e0070b82ba/examples/md/md.py
# Modifications by Adam Atia on 2/7/2025
# Motivation: determine why increased feed flowrates lead to failure to converge (solves at 1 kg/s, fails at 5 kg/s)
# Takeaway: Membrane area should be adjusted with flowrate.

# Even more modifications by Chad Able on 4/23/2025
# Adapting prommis costing with a custom function (using WaterTAPCosting as base)
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

    # Note: MD area is already fixed to 100m2 in the flowsheet.
    m.fs.MD.area.fix(area)
    
    # The initialization routine is tailored to 1 kg/s (uses MD specs attributes to 1 kg/s feed flow)
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

    # assert False
    # Notably, system-level recovery rate of water is set to 50%. I think the 5 kg/s case couldn't solve because more membrane area would be needed to achieve 50% recovery.
    m.fs.overall_recovery.display()

    # NF Permeate conditions
    # m.fs.feed.flow_mass_phase_comp[0,"Liq","H2O"].fix(7.2258)
    # m.fs.feed.flow_mass_phase_comp[0,"Liq","TDS"].fix(0.64491)
    # without NF, feed conditions
    m.fs.feed.flow_mass_phase_comp[0, "Liq", "H2O"].unfix()
    m.fs.feed.flow_mass_phase_comp[0, "Liq", "TDS"].unfix()
    m.fs.feed.properties[0].flow_vol_phase["Liq"].fix(0.014877*0.5)                # volumetric flow rate (m3/s), equal to 235.8 gpm
    m.fs.feed.properties[0].conc_mass_phase_comp["Liq", "TDS"].fix(99.304)        # conc in g/L #base 99.304

    res = MD.solve(m, tee=False)
    if check_optimal_termination(res):
        # m.fs.MD.report()
        m.fs.MD.area.display()
    else:
        print("SOLVE FAILED")
        infeas.print_infeasible_constraints(m)
    
    
       #%% bring in prommis costing
    from prommis.uky.costing.ree_plant_capcost import QGESSCosting, QGESSCostingData
    # Add NF for costing only?
    # import watertap.property_models.multicomp_aq_sol_prop_pack as props

    # from watertap.unit_models.nanofiltration_ZO import NanofiltrationZO
    # from watertap.unit_models.pressure_changer import Pump  
    # import json

    # with open(r"C:\Users\Adam\my-nawi-hub\SA2_009_004_EY24\solute_parameters.json") as f:
    #     solute_data = json.load(f)

    # # solute list
    # solute_list = list(solute_data.keys())
    # mw_data = {key: solute_data[key]['mw'] for key in solute_list}
    # charge = {key: solute_data[key]['charge'] for key in solute_list}
    # diffusivity = {("Liq",key): 1e-9 for key in solute_list}

    # m.fs.properties = props.MCASParameterBlock(solute_list=solute_list,
    #                                            mw_data=mw_data,
    #                                            charge=charge,
    #                                            diffusivity_data=diffusivity,
    #                                            density_calculation=props.DensityCalculation.seawater,
    #                                            material_flow_basis=props.MaterialFlowBasis.mass)

    # # create units
    # # m.fs.feed = Feed(property_package=m.fs.properties)
    # # m.fs.product = Product(property_package=m.fs.properties)
    # # m.fs.disposal = Product(property_package=m.fs.properties)
    # m.fs.nf = NanofiltrationZO(property_package=m.fs.properties)
    # m.fs.P1 = Pump(property_package=m.fs.properties)

    # m.fs.P1.efficiency_pump.fix(0.80)  # pump efficiency [-]
    # m.fs.P1.outlet.pressure[0].fix(10e5)

    # # fully specify system
    # m.fs.nf.properties_permeate[0].pressure.fix(101325)
    # m.fs.nf.recovery_vol_phase.fix(0.5)
    # m.fs.nf.flux_vol_solvent.fix(1.446759259259259e-5)
    # m.fs.nf.area.fix(499.44685)
    # Create QGESS costing block
    m.fs.costing = WaterTAPCosting()
    # Units to include in costing
    watertap_blocks = [
        m.fs.MD,
        m.fs.hx,
        m.fs.heater,
        m.fs.chiller,
        m.fs.mixer,
        m.fs.pump_feed,
        m.fs.pump_brine,
        m.fs.pump_permeate
    ]

    for i in range(len(watertap_blocks)):
        if watertap_blocks[i] == m.fs.chiller:
            watertap_blocks[i].costing = UnitModelCostingBlock(
                flowsheet_costing_block=m.fs.costing,
                costing_method=cost_heater_chiller,
                costing_method_arguments={"HC_type": "chiller"},
            )
        elif watertap_blocks[i] == m.fs.heater:
            watertap_blocks[i].costing = UnitModelCostingBlock(
                flowsheet_costing_block=m.fs.costing,
                costing_method=cost_heater_chiller,
                costing_method_arguments={"HC_type": "electric_heater"},
            )
        else:
            watertap_blocks[i].costing = UnitModelCostingBlock(flowsheet_costing_block=m.fs.costing)
    m.fs.costing.cost_process()
    m.fs.costing.add_annual_water_production(m.fs.permeate.properties[0].flow_vol)
    m.fs.costing.add_LCOW(m.fs.permeate.properties[0].flow_vol)
    m.fs.costing.add_specific_energy_consumption(m.fs.permeate.properties[0].flow_vol)
    m.fs.costing.base_currency = pyunits.USD_2023
    m = QGESS_costing(m=m, units=watertap_blocks, water_flow_rate=pyunits.convert(m.fs.permeate.properties[0].flow_vol,
                                                                                  to_units=pyunits.m ** 3 / pyunits.hr))
    
    # Apply costing with detailed parameters
    # m.fs.costing.build_process_costs(
    #     # Capital cost factors
    #     cost_factor=1.58,
    #     piping_materials_and_labor_percentage=20,
    #     electrical_materials_and_labor_percentage=20,
    #     instrumentation_percentage=8,
    #     plants_services_percentage=10,
    #     process_buildings_percentage=40,
    #     auxiliary_buildings_percentage=15,
    #     site_improvements_percentage=10,
    #     equipment_installation_percentage=17,
    #     field_expenses_percentage=12,
    #     project_management_and_construction_percentage=30,
    #     process_contingency_percentage=15,
    #
    #     # Labor cost parameters
    #     labor_types=[
    #         "skilled",
    #         "unskilled",
    #         "supervisor",
    #         "maintenance",
    #         "technician",
    #         "engineer",
    #     ],
    #     labor_rate=[26.08, 19.08, 30.39, 22.73, 21.97, 45.85],  # USD/hr
    #     labor_burden=25,  # % fringe benefits
    #     operators_per_shift=[2, 0, 0, 0, 0, 0],
    #     hours_per_shift=8,
    #     shifts_per_day=3,
    #     operating_days_per_year=365,
    #
    #     # Product and efficiency parameters
    #     mixed_product_sale_price_realization_factor=0.65,
    #     efficiency=0.80,  # power usage efficiency
    #     resources=[],
    #     rates=[],
    #     # O&M costs
    #     fixed_OM=True,
    #     variable_OM=True,
    #     land_cost=1,
    #     CE_index_year="UKy_2019",
    #
    #     # Units to include in costing
    #     watertap_blocks=[
    #         m.fs.MD,
    #         # m.fs.nf,
    #         # m.fs.P1,
    #         m.fs.hx,
    #         m.fs.heater,
    #         m.fs.mixer,
    #         m.fs.pump_feed,
    #         m.fs.pump_brine,
    #         m.fs.pump_permeate
    #     ]
    # )
    
    # Initialize costing
    # QGESSCostingData.costing_initialization(m.fs.costing)
    # QGESSCostingData.initialize_fixed_OM_costs(m.fs.costing)
    #
    # # Calculate LCOW (Levelized Cost of Water)
    # denominator = pyunits.convert(
    #     m.fs.permeate.properties[0].flow_vol,
    #     to_units=pyunits.m**3 / pyunits.year
    # )
    # m.fs.costing.prommis_LCOW = Expression(
    #     expr=m.fs.costing.annualized_cost / denominator * 1e6
    # )
    
    # Set objective
    assert_units_consistent(m)
    m.fs.objective = Objective(expr=m.fs.costing.QGESS_LCOW)
    

    
    
    
    
    
    recovery_range= 0.5, #np.linspace(0.05,.95,100)
    solve_status = np.zeros(len(recovery_range))
    for ind, i in enumerate(recovery_range):
        m.fs.overall_recovery.fix(i)
        print(f"FIXED RECOVERY TO {i}")
        res = MD.solve(m, tee=True)
        if check_optimal_termination(res):
            # m.fs.MD.report()
            m.fs.MD.area.display()
            solve_status[ind] = 1
        else:
            print("SOLVE FAILED")
            infeas.print_infeasible_constraints(m)
    
    
    print(f"solve status:\n{solve_status}")
    assert_optimal_termination(res)
    # m.fs.nf.area.display()
    m.fs.costing.QGESS_LCOW.display()
    print(value(m.fs.costing.aggregate_flow_costs['electricity']))
    # QGESSCostingData.report(m.fs.costing)
    # QGESSCostingData.display_bare_erected_costs(m.fs.costing)
    # QGESSCostingData.display_flowsheet_cost(m.fs.costing)
        

    # # Let's loop through mass flowrates, from 2 to 5 kg/s. 5 kg/s can solve now.
    # for i in range(2,6):
    #     feed_flow_mass = i # kg/s
    #     m.fs.feed.properties[0].flow_mass_phase_comp["Liq", "TDS"].fix(
    #         feed_flow_mass * feed_mass_frac_TDS
    #     )
    #     feed_mass_frac_H2O = 1 - feed_mass_frac_TDS
    #     m.fs.feed.properties[0].flow_mass_phase_comp["Liq", "H2O"].fix(
    #         feed_flow_mass * feed_mass_frac_H2O
    #     )
    #     res = MD.solve(m, tee=False)
    #     print(f"FLOWRATE = {i}")


    #     if check_optimal_termination(res):
    #         # m.fs.MD.report()
    #         m.fs.MD.area.display()
    #     else:
    #         print("SOLVE FAILED")
    #         infeas.print_infeasible_constraints(m)