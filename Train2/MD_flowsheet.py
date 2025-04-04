from pyomo.environ import (
    ConcreteModel,
    value,
    TransformationFactory,
    units as pyunits,
    assert_optimal_termination,
    Block,
    Objective,
    Expression,
    Constraint,
    assert_optimal_termination
)
import numpy as np
import matplotlib.pyplot as plt
import sys

from nanofiltration.nanofiltration_zo import nanofiltration
from translator.translator import MCAStoSeawaterTranslator
from helpers.helpers import visualize_flowsheet

from pyomo.network import Arc
from pyomo.util.infeasible import log_infeasible_constraints

from idaes.core import FlowsheetBlock, UnitModelCostingBlock
from idaes.core.solvers import get_solver
from idaes.core.util.initialization import propagate_state
from idaes.core.util.tables import generate_table
import logging
logging.getLogger('pyomo.util.infeasible').setLevel(logging.DEBUG)

from md import MD_single_stage_continuous_recirculation as MD
from watertap.core.util.initialization import check_dof
from watertap.costing import WaterTAPCosting
from helpers.helpers import create_plot

sys.path.append('/Users/nicktiwari/Documents/prommis/src/')
from prommis.uky.costing.ree_plant_capcost import QGESSCosting, QGESSCostingData

def md_flowsheet(recovery=0.08):

    # Create model
    m = ConcreteModel()
    m.fs = FlowsheetBlock(dynamic=False)

    # Create nanofiltration 
    nanofiltration(m, solute_file='../solute_parameters.json')

    # Create MD
    m = MD.build(m)
    MD.set_operating_conditions(m)

    # Create translator
    m.fs.translator = MCAStoSeawaterTranslator(inlet_property_package=m.fs.properties,
                                              outlet_property_package=m.fs.properties_hot_ch)
    # Connect translator
    m.fs.nf_to_translator = Arc(source=m.fs.nf.permeate, destination=m.fs.translator.inlet)

    TransformationFactory("network.expand_arcs").apply_to(m)

    # Constraints ensure MD feed and NF outlet match
    m.fs.eq_tds = Constraint(
        expr=m.fs.translator.properties_out[0].flow_mass_phase_comp["Liq", "TDS"] ==
        m.fs.feed.properties[0].flow_mass_phase_comp["Liq", "TDS"]
        )

    m.fs.eq_h2o = Constraint(
        expr=m.fs.translator.properties_out[0].flow_mass_phase_comp["Liq", "H2O"] ==
        m.fs.feed.properties[0].flow_mass_phase_comp["Liq", "H2O"]
        )

    # Fix the area of the NF unit (you may want to change this)
    m.fs.nf.area.fix()

    # MD recovery (vary this)
    m.fs.overall_recovery.fix(recovery)

    # Initialize
    propagate_state(m.fs.nf_to_translator)
    m.fs.translator.initialize()

    # Check DOF
    check_dof(m)

    # Initialize MD and NF
    m.fs.nf.initialize()
    MD.initialize_system(m)

    # Remove bounds on MD area, width, length
    m.fs.MD.area.setub(None) 
    m.fs.MD.length.setub(None)
    m.fs.MD.width.setub(None)

#    denominator = pyunits.convert(m.fs.RO.mixed_permeate[0].flow_vol, to_units=pyunits.m**3 / pyunits.year)
#    m.fs.costing.prommis_LCOW = Expression(expr=m.fs.costing2.annualized_cost / denominator * 1e6)

    # Costing blocks
    m.fs.costing2 = QGESSCosting()

    m.fs.land_cost = 1

    m.fs.costing2.build_process_costs(
        # arguments related to installation costs
        piping_materials_and_labor_percentage=20,
        electrical_materials_and_labor_percentage=20,
        instrumentation_percentage=8,
        plants_services_percentage=10,
        process_buildings_percentage=40,
        auxiliary_buildings_percentage=15,
        site_improvements_percentage=10,
        equipment_installation_percentage=17,
        field_expenses_percentage=12,
        project_management_and_construction_percentage=30,
        process_contingency_percentage=15,
        # argument related to Fixed OM costs
        labor_types=[
            "skilled",
            "unskilled",
            "supervisor",
            "maintenance",
            "technician",
            "engineer",
        ],
        labor_rate=[24.98, 19.08, 30.39, 22.73, 21.97, 45.85],  # USD/hr
        labor_burden=25,  # % fringe benefits
        operators_per_shift=[4, 9, 2, 2, 2, 3],
        hours_per_shift=8,
        shifts_per_day=3,
        operating_days_per_year=336,
        mixed_product_sale_price_realization_factor=0.65,  # 65% price realization for mixed products
        # arguments related to total owners costs
        land_cost=m.fs.land_cost,
        resources=[],
        rates=[],
        fixed_OM=True,
        variable_OM=True,
        feed_input=None,
        efficiency=0.80,  # power usage efficiency, or fixed motor/distribution efficiency
        waste=[],
        recovery_rate_per_year=None,
        CE_index_year="UKy_2019",
        watertap_blocks = [m.fs.MD, m.fs.nf, m.fs.P1, m.fs.hx, m.fs.heater, m.fs.mixer, m.fs.pump_feed, m.fs.pump_brine, m.fs.pump_permeate]

    )

    QGESSCostingData.costing_initialization(m.fs.costing2)
    QGESSCostingData.initialize_fixed_OM_costs(m.fs.costing2)

    # Solve
    MD.optimize_set_up(m)
    MD.interval_initializer(m)
    MD.solve(m)

    return m

def vary_recovery():
    area = []
    recoveries = np.arange(0.08, 0.094, 0.001)
    for recovery in recoveries:
        m = md_flowsheet(recovery=recovery)
        area.append(value(m.fs.MD.area))
    return recoveries, area

def nf_df_concentrations(m):

    comps = [('conc_mass_phase_comp', ('Liq', comp)) for comp in m.fs.properties.component_list]

    stream_dict = {
        "Feed Inlet": m.fs.nf.feed_side.properties_in[0],
        "Feed Outlet": m.fs.nf.feed_side.properties_out[0],
        "Permeate": m.fs.nf.properties_permeate[0]        
    }

    df = generate_table(stream_dict, comps).T * 1000 # convert to mg/L
 
    df.index = [f"{idx[1][1]} mass concentration (mg/L)" for idx in df.index]
    df.drop('H2O mass concentration (mg/L)', inplace=True)
    df = df.round(2)

    return df 

if __name__ == '__main__':
    m = md_flowsheet()
    #recoveries, area = vary_recovery()
    df = nf_df_concentrations(m)
    print(df)
    df.to_html('temp.html')

    # Create the plot
    # plot = create_plot(
    #     x_data=nf_area, 
    #     y_data=[area], 
    #     x_label="Recovery (dimensionless)", 
    #     y_label="Area (m$^2$)",
    # )
    # plt.savefig('recovery_area.png', dpi=400)
    # plt.show()

    #visualize_flowsheet(m)
