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
    units
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
from watertap.core.util.initialization import check_dof
from watertap.costing import WaterTAPCosting

sys.path.append('E:/codes/SA2_009_004_EY24')
sys.path.append('E:/codes/SA2_009_004_EY24/prommis/src')
from prommis.uky.costing.ree_plant_capcost import QGESSCosting, QGESSCostingData
from prommis_costing import QGESS_costing
# sys.path.append('/Users/nicktiwari/Documents/prommis/src/')
# print(sys.path)
#from prommis.uky.costing.ree_plant_capcost import QGESSCosting, QGESSCostingData

def nanofiltration(m, Q_in = 0.014877, solute_file = '../solute_parameters2.json'):
    # Read data from 'solute_parameters.json'
    with open(solute_file) as f:
        solute_data = json.load(f)

    # solute list
    solute_list = list(solute_data.keys())
    mw_data = {key: solute_data[key]['mw'] for key in solute_list}
    charge = {key: solute_data[key]['charge'] for key in solute_list}

    m.fs.properties = props.MCASParameterBlock(solute_list=solute_list,
                                               mw_data=mw_data,
                                               charge=charge,
                                               density_calculation=props.DensityCalculation.seawater)

    # create units
    m.fs.feed_nf = Feed(property_package=m.fs.properties)
    m.fs.product = Product(property_package=m.fs.properties)
    m.fs.disposal = Product(property_package=m.fs.properties)
    m.fs.nf = NanofiltrationZO(property_package=m.fs.properties)
    m.fs.P1 = Pump(property_package=m.fs.properties)

    # connections
    m.fs.feed_to_p1 = Arc(source=m.fs.feed_nf.outlet, destination=m.fs.P1.inlet)
    m.fs.p1_to_nf = Arc(source=m.fs.P1.outlet, destination=m.fs.nf.inlet)
    m.fs.s03 = Arc(source=m.fs.nf.permeate, destination=m.fs.product.inlet)
    m.fs.s04 = Arc(source=m.fs.nf.retentate, destination=m.fs.disposal.inlet)

    TransformationFactory("network.expand_arcs").apply_to(m)

    # specify flowsheet
    m.fs.feed_nf.properties[0].pressure.fix(101325)  # feed pressure [Pa]
    m.fs.feed_nf.properties[0].temperature.fix(273.15 + 25)  # feed temperature [K]

    # properties (cannot be fixed for initialization routines, must calculate the state variables)
    var_args = {("conc_mass_phase_comp", ("Liq", key)): \
                solute_data[key]['mass_conc_mg_L']/1000 for key in solute_list} # Convert mg/L to kg/m3

    var_args[("flow_vol_phase", ("Liq"))] = Q_in
    m.fs.feed_nf.properties[0].total_dissolved_solids
    m.fs.feed_nf.properties.calculate_state(
        var_args = var_args,  # feed mass fractions [-]
        hold_state=True,  # fixes the calculated component mass flow rates
    )
    m.fs.feed_nf.properties[0].assert_electroneutrality(defined_state=True,
                                                     adjust_by_ion='Cl')
    m.fs.P1.efficiency_pump.fix(0.80)  # pump efficiency [-]
    m.fs.P1.outlet.pressure[0].fix(10e5)

    # fully specify system
    m.fs.nf.properties_permeate[0].pressure.fix(101325)
    m.fs.nf.recovery_vol_phase.fix(0.5)

    for key in solute_list:
        if key != "Cl":
            m.fs.nf.rejection_phase_comp[0, "Liq", key].fix(solute_data[key]['rejection_phase_comp'])

    m.fs.nf.rejection_phase_comp[0, "Liq", "Cl"] = 0.15  # guess, but electroneutrality enforced below
    charge_comp = {key: solute_data[key]['charge'] for key in solute_list}

    m.fs.nf.eq_electroneutrality = Constraint(
        expr=0
        == sum(
            charge_comp[j]
            * m.fs.nf.properties_permeate[0].conc_mol_phase_comp["Liq", j]
            for j in charge_comp
        )
    )
    constraint_scaling_transform(m.fs.nf.eq_electroneutrality, 1)

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
            "flow_mass_phase_comp", inverse_order_of_magnitude(solute_data[key]['mass_conc_mg_L']/1000), index=("Liq", key)
         )

    m.fs.nf.feed_side.properties_in[0].total_dissolved_solids
    m.fs.nf.feed_side.properties_out[0].total_dissolved_solids

    m.fs.nf.properties_permeate[0].total_dissolved_solids
    iscale.set_scaling_factor(m.fs.P1.control_volume.work, 1e-3)

    iscale.calculate_scaling_factors(m)

    # initialize
    m.fs.feed_nf.initialize()
    propagate_state(m.fs.feed_to_p1)
    m.fs.P1.initialize()
    propagate_state(m.fs.p1_to_nf)
    m.fs.nf.initialize()

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
        watertap_blocks = [m.fs.nf, m.fs.P1]
    )
    QGESSCostingData.costing_initialization(m.fs.costing2)
    QGESSCostingData.initialize_fixed_OM_costs(m.fs.costing2)

def QGESS_costs(m):
    m.fs.costing = WaterTAPCosting()
    m.fs.nf.costing = UnitModelCostingBlock(flowsheet_costing_block=m.fs.costing)
    m.fs.P1.costing = UnitModelCostingBlock(flowsheet_costing_block=m.fs.costing)
    m.fs.costing.cost_process()
    m.fs.costing.add_annual_water_production(m.fs.product.properties[0].flow_vol)
    m.fs.costing.add_LCOW(m.fs.product.properties[0].flow_vol)
    m.fs.costing.add_specific_energy_consumption(m.fs.product.properties[0].flow_vol)
    m.fs.costing.base_currency = units.USD_2023
    watertap_blocks = [m.fs.nf, m.fs.P1]
    m = QGESS_costing(m=m, units=watertap_blocks, water_flow_rate=units.convert(m.fs.product.properties[0].flow_vol, to_units=units.m ** 3 / units.hr))

    return m

def main():
    model = ConcreteModel()
    model.fs = FlowsheetBlock(dynamic=False)
    nanofiltration(model)
    QGESS_costs(model)
    solver = get_solver()
    solver.solve(model)
#    QGESSCostingData.report(model.fs.costing2)
#    QGESSCostingData.display_flowsheet_cost(model.fs.costing2)

    model.fs.nf.report()
    model.fs.nf.properties_permeate[0.0].display()
    print(value(model.fs.costing.QGESS_LCOW))
    model.fs.nf.properties_permeate[0].total_dissolved_solids.display()
    model.fs.nf.properties_permeate[0].flow_vol.display()
    return model

if __name__ == "__main__":
    m = main()