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
from NF_ZO import nanofiltration

solver = get_solver()
m = ConcreteModel()
m.fs = FlowsheetBlock(dynamic=False)

nanofiltration(m)


iscale.calculate_scaling_factors(m)

# solve model
results = solver.solve(m, tee=True)
m.fs.unit.report()

# print the Ba Molar Concentration @Inlet for fs.unit
print(m.fs.unit.properties_permeate[0].conc_mol_phase_comp["Liq", "Ba"].value)

