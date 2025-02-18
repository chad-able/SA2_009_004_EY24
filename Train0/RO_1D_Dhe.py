#################################################################################
# WaterTAP Copyright (c) 2020-2023, The Regents of the University of California,
# through Lawrence Berkeley National Laboratory, Oak Ridge National Laboratory,
# National Renewable Energy Laboratory, and National Energy Technology
# Laboratory (subject to receipt of any required approvals from the U.S. Dept.
# of Energy). All rights reserved.
#
# Please see the files COPYRIGHT.md and LICENSE.md for full copyright and license
# information, respectively. These files are also available online at the URL
# "https://github.com/watertap-org/watertap/"
#################################################################################

# imports
from pyomo.environ import (
    ConcreteModel,
    value,
    TransformationFactory,
    units as pyunits,
    assert_optimal_termination,
    Block,
    Objective,
    Expression
)

import numpy as np
import json
from pyomo.environ import units as pyunits
import pandas as pd

from pyomo.network import Arc
from idaes.core import FlowsheetBlock
from idaes.core.solvers import get_solver
from idaes.core.util.initialization import propagate_state
from idaes.models.unit_models import Product, Feed
from idaes.core import UnitModelCostingBlock
import idaes.core.util.scaling as iscale
from pyomo.util.check_units import assert_units_consistent
from watertap.unit_models.reverse_osmosis_1D import (
    ReverseOsmosis1D,
    ConcentrationPolarizationType,
    MassTransferCoefficient,
    PressureChangeType,
)

import sys
sys.path.append('/Users/nicktiwari/Documents/watertap/')
from watertap.unit_models.pressure_changer import Pump
from watertap.costing import WaterTAPCosting
from watertap.core.wt_database import Database
import watertap.property_models.seawater_prop_pack as prop_SW
import time
import idaes.logger as idaeslog
from NF_ZO import nanofiltration

sys.path.append('/Users/nicktiwari/Documents/prommis/src/')
from prommis.uky.costing.ree_plant_capcost import QGESSCosting, QGESSCostingData

def RO_1D_Dhe(process_variable = "recovery", process_value = 0.2, vis=False):

    # Check to see if recovery is between 0 and 1
    # get solver
    solver = get_solver()

    # setup flowsheet
    m = ConcreteModel()
    m.fs = FlowsheetBlock(dynamic=False)
    m.fs.prop_desal = prop_SW.SeawaterParameterBlock()

    # Nanofiltration
    m2 = ConcreteModel()
    m2.fs = FlowsheetBlock(dynamic=False)
    nanofiltration(m2)

    # costing
    m.fs.costing2 = QGESSCosting()
    m.fs.costing = WaterTAPCosting()

    # create units
    m.fs.feed = Feed(property_package=m.fs.prop_desal)

    m.fs.P1 = Pump(property_package=m.fs.prop_desal)
    m.fs.P1.costing = UnitModelCostingBlock(flowsheet_costing_block=m.fs.costing)

    m.fs.RO = ReverseOsmosis1D(
        property_package=m.fs.prop_desal,
        has_pressure_change=False,
        pressure_change_type=PressureChangeType.fixed_per_stage,
        mass_transfer_coefficient=MassTransferCoefficient.none,
        concentration_polarization_type=ConcentrationPolarizationType.none,
    )
    m.fs.RO.costing = UnitModelCostingBlock(flowsheet_costing_block=m.fs.costing)
    m.fs.costing.cost_process()
    m.fs.costing.add_specific_energy_consumption(m.fs.RO.mixed_permeate[0].flow_vol)
    m.fs.costing.add_LCOW(m.fs.RO.mixed_permeate[0].flow_vol)

    # connections
    m.fs.s01 = Arc(source=m.fs.feed.outlet, destination=m.fs.P1.inlet)
    m.fs.s02 = Arc(source=m.fs.P1.outlet, destination=m.fs.RO.inlet)

    TransformationFactory("network.expand_arcs").apply_to(m)

    # specify flowsheet
    m.fs.feed.properties[0].pressure.fix(101325)  # feed pressure [Pa]
    m.fs.feed.properties[0].temperature.fix(273.15 + 25)  # feed temperature [K]
    # properties (cannot be fixed for initialization routines, must calculate the state variables)

    m.fs.feed.properties[0].mass_frac_phase_comp["Liq", "TDS"] = 0.101  # feed TDS mass fraction [-]
    m.fs.feed.properties.calculate_state(
        var_args={
            ("flow_mass_phase_comp", ("Liq", "H2O")): 100,  # feed mass flow rate [kg/s]
            ("mass_frac_phase_comp", ("Liq", "TDS")): value(
                m.fs.feed.properties[0].mass_frac_phase_comp["Liq", "TDS"])
        },  # feed TDS mass fraction [-]
        hold_state=True,  # fixes the calculated component mass flow rates
    )
    m.fs.P1.efficiency_pump.fix(0.80)  # pump efficiency [-]
    m.fs.P1.outlet.pressure[0].fix(70e5)
    membrane_area = 12100 #membrane area = 50 * feed flow mass(kg/s) according to NF Test
    A = 4.2e-12
    B = 3.5e-8
    pressure_atmospheric = 101325
    m.fs.RO.area.fix(membrane_area)
    m.fs.RO.A_comp.fix(A)
    m.fs.RO.B_comp.fix(B)
    m.fs.RO.permeate.pressure[0].fix(pressure_atmospheric)
    m.fs.RO.length.fix(16)

    # scaling
    m.fs.prop_desal.set_default_scaling("flow_mass_phase_comp", 1e-3, index=("Liq", "H2O"))
    m.fs.prop_desal.set_default_scaling(
        "flow_mass_phase_comp", 1e-2, index=("Liq", "TDS")
    )
    iscale.set_scaling_factor(m.fs.P1.control_volume.work, 1e-3)
    iscale.set_scaling_factor(m.fs.RO.area, 1e-5)

    iscale.calculate_scaling_factors(m)

    # initialize
    m.fs.feed.initialize()
    propagate_state(m.fs.s01)
    m.fs.P1.initialize()
    propagate_state(m.fs.s02)
    m.fs.RO.initialize(outlvl=idaeslog.DEBUG)


    # solve model
    solver.options['max_iter'] = 100000
    results = solver.solve(m, tee=True)

    #Start optimizing
    m.fs.RO.area.unfix()                  # membrane area (m^2)
    m.fs.P1.outlet.pressure[0].unfix()     # feed pressure (Pa)
    m.fs.RO.length.unfix()
    m.fs.RO.area.setlb(1)
    m.fs.RO.area.setub(None)
    m.fs.P1.outlet.pressure[0].setlb(1e5)
    m.fs.P1.outlet.pressure[0].setub(None)
    CE_index_year = "UKy_2019"

    fix_variable = {
        "area": m.fs.RO.area.fix,
        "recovery": m.fs.RO.recovery_vol_phase[0,'Liq'].fix, 
    }

    fix_variable[process_variable](process_value)

    m.fs.land_cost = 1
    # Expression(
    #     expr=0.303736
    #     * 1e-6
    #     * getattr(units, "MUSD_" + CE_index_year)
    #     / units.ton
    #     * units.convert(m.fs.pump.flow_vol, to_units=units.ton / units.hr)
    #     * hours_per_shift
    #     * units.hr
    #     * shifts_per_day
    #     * units.day**-1
    #     * operating_days_per_year
    #     * units.day
    # )

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
        watertap_blocks = [m.fs.RO, m.fs.P1]

    )

    denominator = pyunits.convert(m.fs.RO.mixed_permeate[0].flow_vol, to_units=pyunits.m**3 / pyunits.year)
    m.fs.costing.prommis_LCOW = Expression(expr=m.fs.costing2.annualized_cost / denominator * 1e6)

    QGESSCostingData.costing_initialization(m.fs.costing2)
    QGESSCostingData.initialize_fixed_OM_costs(m.fs.costing2)

    # consistent units
    assert_units_consistent(m)

    # optimize
    m.fs.objective = Objective(expr=m.fs.costing.prommis_LCOW)
    optimization_results = solver.solve(m)
    nf_results = solver.solve(m2)
    assert_optimal_termination(results)

    QGESSCostingData.report(m.fs.costing2, export=True)
    QGESSCostingData.display_flowsheet_cost(m.fs.costing2)

    #print
    m.fs.feed.report()
    m.fs.P1.report()
    m.fs.RO.report()
    df = m.fs.RO._get_stream_table_contents()
    pd.options.display.float_format = '{:,.10f}'.format
    df.to_csv('stream_table_contents.csv', index=False, float_format='%.10f')


    # Dictionary for results
    results = { "SEC": value(m.fs.costing.specific_energy_consumption),
                "LCOW": value(m.fs.costing.prommis_LCOW),
                "Watertap LCOW": value(m.fs.costing.LCOW),
                "Permeate Flow": value(m.fs.RO.mixed_permeate[0].flow_vol),
                "Brine Flow": value(m.fs.RO.feed_side.properties[0, 1].flow_vol),
                "Pump Pressure": value(m.fs.P1.outlet.pressure[0]),
                "Membrane Area": value(m.fs.RO.area),
                "Recovery": value(m.fs.RO.recovery_vol_phase[0,'Liq']),
                "Variable OM Cost": value(m.fs.costing2.total_variable_OM_cost[0]),
                "Fixed OM Cost": value(m.fs.costing2.total_fixed_OM_cost),
                }


    print("Permeate flow (m3/s): " + "{:.4f}".format(value(m.fs.RO.mixed_permeate[0].flow_vol)))
    print("Brine flow (m3/s): " + "{:.4f}".format(value(m.fs.RO.feed_side.properties[0, 1].flow_vol)))

    print(
            "Energy Consumption: %.1f kWh/m3"
            % value(m.fs.costing.specific_energy_consumption)
        )

    # MUSD/year
    flowrate_year = pyunits.convert(m.fs.RO.mixed_permeate[0].flow_vol, to_units=pyunits.m**3 / pyunits.year)

    print(
        "PROMMIS LCOW: %.2f USD/ton"
        % value(m.fs.costing.LCOW)
        )



    if value(m.fs.P1.outlet.pressure[0]) >= 85e5:
        print("INFEASIBLE") #not feasible to operate conventional RO membranes above this pressure

    if vis:
        m.fs.visualize("Flowsheet")
        try:
            print("Type ^C to stop the program")
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("Program stopped")


    return results

# Encoder to convert numpy objects for json serialization
class NpEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super(NpEncoder, self).default(obj)

def multiple():

    process_variable = "recovery"
    process_value = np.arange(0.2, 0.6, 0.05)
    results = {}

    for pv in process_value:
        result = RO_1D_Dhe(process_variable=process_variable, process_value=pv)
        if process_value == "area":
            results[int(pv)] = result
        else:
            results[pv] = result

    # write results to json files
    with open(f'results_fixed_{process_variable}.json', 'w') as f:
        json.dump(results, f, indent=4, cls=NpEncoder)

def single():
    result = RO_1D_Dhe(process_variable='recovery', process_value=0.45)


if __name__ == '__main__':
    single()

