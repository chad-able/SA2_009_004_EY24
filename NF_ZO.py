# imports
from pyomo.environ import (
    ConcreteModel,
    value,
    TransformationFactory,
    units as pyunits,
    assert_optimal_termination,
    Block,
    Constraint,
    Objective,
)
import json
import math
import sys
from pyomo.network import Arc
from idaes.core import FlowsheetBlock
from idaes.core.solvers import get_solver
from idaes.models.unit_models.translator import Translator
from idaes.core.util.initialization import propagate_state
from idaes.models.unit_models import Product, Feed
from idaes.core import UnitModelCostingBlock
import idaes.core.util.scaling as iscale
from pyomo.util.check_units import assert_units_consistent
from watertap.unit_models.nanofiltration_ZO import NanofiltrationZO
from watertap.unit_models.pressure_changer import Pump
from watertap.core.wt_database import Database
import watertap.property_models.multicomp_aq_sol_prop_pack as props
from idaes.core.util.scaling import (
    calculate_scaling_factors,
    constraint_scaling_transform,
    unscaled_variables_generator,
    unscaled_constraints_generator,
    badly_scaled_var_generator,
)

sys.path.append('/Users/nicktiwari/Documents/prommis/src/')
from prommis.uky.costing.ree_plant_capcost import QGESSCosting, QGESSCostingData

def nanofiltration(m):
    # Read data from 'solute_parameters.json'
    with open("solute_parameters.json") as f:
        solute_data = json.load(f)

    # solute list
    solute_list = list(solute_data.keys())
    mw_data = {key: solute_data[key]['mw'] for key in solute_list}
    charge = {key: solute_data[key]['charge'] for key in solute_list}

    m.fs.properties = props.MCASParameterBlock(solute_list=solute_list,
                                               mw_data=mw_data,
                                               charge=charge)

    # create units
    m.fs.feed = Feed(property_package=m.fs.properties)
    m.fs.product = Product(property_package=m.fs.properties)
    m.fs.disposal = Product(property_package=m.fs.properties)
    m.fs.unit = NanofiltrationZO(property_package=m.fs.properties)
    m.fs.P1 = Pump(property_package=m.fs.properties)

    # connections
    m.fs.s01 = Arc(source=m.fs.feed.outlet, destination=m.fs.P1.inlet)
    m.fs.s02 = Arc(source=m.fs.P1.outlet, destination=m.fs.unit.inlet)
    m.fs.s03 = Arc(source=m.fs.unit.permeate, destination=m.fs.product.inlet)
    m.fs.s04 = Arc(source=m.fs.unit.retentate, destination=m.fs.disposal.inlet)

    TransformationFactory("network.expand_arcs").apply_to(m)

    # specify flowsheet
    m.fs.feed.properties[0].pressure.fix(101325)  # feed pressure [Pa]
    m.fs.feed.properties[0].temperature.fix(273.15 + 25)  # feed temperature [K]

    # properties (cannot be fixed for initialization routines, must calculate the state variables)
    for key in solute_list:
        m.fs.feed.properties[0].flow_mass_phase_comp["Liq", key] = solute_data[key]['mass_concentration']

    var_args = {("flow_mass_phase_comp", ("Liq", key)): solute_data[key]['mass_concentration'] for key in solute_list}
    var_args[("flow_mass_phase_comp", ("Liq", "H2O"))] = 100

    m.fs.feed.properties.calculate_state(
        var_args = var_args,  # feed mass fractions [-]
        hold_state=True,  # fixes the calculated component mass flow rates
    )
    m.fs.P1.efficiency_pump.fix(0.80)  # pump efficiency [-]
    m.fs.P1.outlet.pressure[0].fix(10e5)

    # fully specify system
    m.fs.unit.properties_permeate[0].pressure.fix(101325)
    m.fs.unit.recovery_vol_phase.fix(0.5)

    for key in solute_list:
        if key != "Cl":
            m.fs.unit.rejection_phase_comp[0, "Liq", key].fix(solute_data[key]['rejection_phase_comp'])

    m.fs.unit.rejection_phase_comp[0, "Liq", "Cl"] = 0.15  # guess, but electroneutrality enforced below
    charge_comp = {key: solute_data[key]['charge'] for key in solute_list}

    m.fs.unit.eq_electroneutrality = Constraint(
        expr=0
        == sum(
            charge_comp[j]
            * m.fs.unit.feed_side.properties_out[0].conc_mol_phase_comp["Liq", j]
            for j in charge_comp
        )
    )
    constraint_scaling_transform(m.fs.unit.eq_electroneutrality, 1)

    def inverse_order_of_magnitude(number):
        if number == 0:
            return "undefined"  # The order of magnitude for zero is undefined
        magnitude = math.floor(math.log10(abs(number)))
        return 10**(-magnitude)

    # scaling
    m.fs.properties.set_default_scaling(
        "flow_mass_phase_comp", 1e-2, index=("Liq", "H2O")
    )

    # Set the scaling to be the inverse of the order of magnitude of the mass concentration
    for key in solute_list:
        m.fs.properties.set_default_scaling(
            "flow_mass_phase_comp", inverse_order_of_magnitude(solute_data[key]['mass_concentration']), index=("Liq", key)
         )


    iscale.set_scaling_factor(m.fs.P1.control_volume.work, 1e-3)

    iscale.calculate_scaling_factors(m)

    # initialize
    m.fs.feed.initialize()
    propagate_state(m.fs.s01)
    m.fs.P1.initialize()
    propagate_state(m.fs.s02)
    m.fs.unit.initialize()
    propagate_state(m.fs.s03)
    m.fs.product.initialize()
    propagate_state(m.fs.s04)
    m.fs.disposal.initialize()

    return m

def qgess_costing(m):
    m.fs.costing2 = QGESSCosting()
    CE_index_year = "UKy_2019"
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
        watertap_blocks = [m.fs.unit, m.fs.P1]
    )
    QGESSCostingData.costing_initialization(m.fs.costing2)
    QGESSCostingData.initialize_fixed_OM_costs(m.fs.costing2)


def main():
    model = ConcreteModel()
    model.fs = FlowsheetBlock(dynamic=False)
    nanofiltration(model)
    qgess_costing(model)
    solver = get_solver()
    solver.solve(model)
    QGESSCostingData.report(model.fs.costing2)
    QGESSCostingData.display_flowsheet_cost(model.fs.costing2)

    model.fs.unit.report()

if __name__ == "__main__":
    main()
