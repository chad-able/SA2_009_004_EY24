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
    Constraint,
    Objective,
)
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
# get solver
solver = get_solver()

# setup flowsheet
m = ConcreteModel()
m.fs = FlowsheetBlock(dynamic=False)

# solute list
solute_list = ["Ca_2+", "Mg_2+", "Cl_-", "Na_+"]
mw_data = {"Ca_2+": 40e-3, "Mg_2+": 24e-3, "Cl_-": 35e-3, "Na_+": 23e-3}
charge = {"Ca_2+": 2, "Mg_2+": 2, "Cl_-": -1, "Na_+": 1}

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
m.fs.feed.properties[0].mass_frac_phase_comp["Liq", "Ca_2+"] = 0.000891
m.fs.feed.properties[0].mass_frac_phase_comp["Liq", "Mg_2+"] = 0.002878
m.fs.feed.properties[0].mass_frac_phase_comp["Liq", "Cl_-"] = 0.04366
m.fs.feed.properties[0].mass_frac_phase_comp["Liq", "Na_+"] = 0.02465

m.fs.feed.properties.calculate_state(
    var_args={
        ("flow_mass_phase_comp", ("Liq", "H2O")): 436.346,  # feed mass flow rate [kg/s]
        ("mass_frac_phase_comp", ("Liq", "Ca_2+")): 0.000891,
        ("mass_frac_phase_comp", ("Liq", "Mg_2+")): 0.002878,
        ("mass_frac_phase_comp", ("Liq", "Cl_-")): 0.04366,
        ("mass_frac_phase_comp", ("Liq", "Na_+")): 0.02465,
    },  # feed mass fractions [-]
    hold_state=True,  # fixes the calculated component mass flow rates
)
m.fs.P1.efficiency_pump.fix(0.80)  # pump efficiency [-]
m.fs.P1.outlet.pressure[0].fix(10e5)

# fully specify system
m.fs.unit.properties_permeate[0].pressure.fix(101325)
m.fs.unit.recovery_vol_phase.fix(0.6)
m.fs.unit.rejection_phase_comp[0, "Liq", "Na_+"].fix(0.01)
m.fs.unit.rejection_phase_comp[0, "Liq", "Ca_2+"].fix(0.79)
m.fs.unit.rejection_phase_comp[0, "Liq", "Mg_2+"].fix(0.94)
m.fs.unit.rejection_phase_comp[0, "Liq", "Cl_-"] = 0.15  # guess, but electroneutrality enforced below
charge_comp = {"Na_+": 1, "Ca_2+": 2, "Mg_2+": 2, "Cl_-": -1, 
               }
m.fs.unit.eq_electroneutrality = Constraint(
    expr=0
    == sum(
        charge_comp[j]
        * m.fs.unit.feed_side.properties_out[0].conc_mol_phase_comp["Liq", j]
        for j in charge_comp
    )
)
constraint_scaling_transform(m.fs.unit.eq_electroneutrality, 1)

# scaling
m.fs.properties.set_default_scaling(
    "flow_mass_phase_comp", 1e-2, index=("Liq", "H2O")
)
m.fs.properties.set_default_scaling(
    "flow_mass_phase_comp", 1e-1, index=("Liq", "Na_+")
)
m.fs.properties.set_default_scaling(
    "flow_mass_phase_comp", 1e1, index=("Liq", "Ca_2+")
)
m.fs.properties.set_default_scaling(
    "flow_mass_phase_comp", 1, index=("Liq", "Mg_2+")
)
m.fs.properties.set_default_scaling(
    "flow_mass_phase_comp", 1e-1, index=("Liq", "Cl_-")
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

# solve model
results = solver.solve(m, tee=True)
m.fs.unit.report()
