from pyomo.environ import ConcreteModel

from idaes.core import FlowsheetBlock
from watertap.core.solvers import get_solver

from watertap.core.wt_database import Database
from watertap.core.zero_order_properties import WaterParameterBlock
from watertap.unit_models.zero_order import NanofiltrationZO


def main():

    # Create a Pyomo model and initialize the YAML database
    model = ConcreteModel()
    model.db = Database()

    # Create an IDAES flowsheet and define the solutes
    model.fs = FlowsheetBlock(dynamic=False)
    model.fs.params = WaterParameterBlock(solute_list=["nonvolatile_toc", "toc", "manganese"])

    # Setup the zero-order model and define inlet flows
    model.fs.unit = NanofiltrationZO(property_package=model.fs.params, database=model.db)
    model.fs.unit.inlet.flow_mass_comp[0, "H2O"].fix(10)
    model.fs.unit.inlet.flow_mass_comp[0, "nonvolatile_toc"].fix(1)
    model.fs.unit.inlet.flow_mass_comp[0, "toc"].fix(1)
    model.fs.unit.inlet.flow_mass_comp[0, "manganese"].fix(1)

    # Load default parameters from the YAML database
    model.fs.unit.load_parameters_from_database()

    # Access the solver and solve the model
    solver = get_solver()
    solver.solve(model)

    # Display a report of the results
    model.fs.unit.report()


if __name__ == "__main__":
    main()
