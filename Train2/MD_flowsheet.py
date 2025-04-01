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

from nanofiltration.nanofiltration_zo import nanofiltration
from translator.translator import MCAStoSeawaterTranslator
from helpers.helpers import visualize_flowsheet

from pyomo.network import Arc
from pyomo.util.infeasible import log_infeasible_constraints

from idaes.core import FlowsheetBlock
from idaes.core.solvers import get_solver
from idaes.core.util.initialization import propagate_state
from idaes.core.util.tables import generate_table
import logging
logging.getLogger('pyomo.util.infeasible').setLevel(logging.DEBUG)

from md import MD_single_stage_continuous_recirculation as MD
from watertap.core.util.initialization import check_dof
from helpers.helpers import create_plot

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
