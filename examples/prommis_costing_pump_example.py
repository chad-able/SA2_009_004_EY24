from pyomo.environ import (
    ConcreteModel,
    Constraint,
    Expression,
    Param,
    SolverFactory,
    Suffix,
    TransformationFactory,
    Var,
    check_optimal_termination,
    units,
    value,
)
from idaes.core import FlowsheetBlock, UnitModelBlock, UnitModelCostingBlock
from idaes.core.solvers import get_solver
import sys
sys.path.append('/Users/nicktiwari/Documents/prommis/src/')
from prommis.uky.costing.ree_plant_capcost import QGESSCosting, QGESSCostingData

def cost_pump_example():
    """Example of costing a pump using the QGESS costing framework."""
    # Create a model
    m = ConcreteModel()
    m.fs = FlowsheetBlock(dynamic=False)
    
    # Add costing
    m.fs.costing = QGESSCosting()
    
    # Create a pump block
    m.fs.pump = UnitModelBlock()
    
    # Define and fix the pump flow rate
    m.fs.pump.flow_vol = Var(initialize=100, units=units.l/units.hour)
    m.fs.pump.flow_vol.fix()
    
    # Add costing to the pump using QGESS costing data
    pump_accounts = ["4.4"]  # UKy Process Pump account number
    m.fs.pump.costing = UnitModelCostingBlock(
        flowsheet_costing_block=m.fs.costing,
        costing_method=QGESSCostingData.get_REE_costing,
        costing_method_arguments={
            "cost_accounts": pump_accounts,
            "scaled_param": m.fs.pump.flow_vol,
            "source": 1,  # UKy source
            "n_equip": 1,  # Number of pumps
            "scale_down_parallel_equip": False,
            "CE_index_year": "UKy_2019",
        },
    )

    CE_index_year = "UKy_2019"

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

    m.fs.costing.build_process_costs(
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
        variable_OM=False,
        feed_input=None,
        efficiency=0.80,  # power usage efficiency, or fixed motor/distribution efficiency
        waste=[],
        recovery_rate_per_year=None,
        CE_index_year="UKy_2019",
    )

    # Initialize costing
    QGESSCostingData.costing_initialization(m.fs.costing)
    QGESSCostingData.initialize_fixed_OM_costs(m.fs.costing)

    # Initialize and solve
    solver = get_solver()
    results = solver.solve(m)
    
    # Print results
    print("\nPump Costing Results")
    print("-" * 50)
    print(value(m.fs.pump.flow_vol))

#    print(f"Total installed cost: ${value(m.fs.pump.costing.installation_cost):.2f}")
    
    return m

def display_costing(m):
    """
    Print the key costing results.

    Args:
        m: pyomo model
    """
    QGESSCostingData.report(m.fs.costing)
    QGESSCostingData.display_bare_erected_costs(m.fs.costing)
    QGESSCostingData.display_flowsheet_cost(m.fs.costing)


if __name__ == "__main__":
    m = cost_pump_example()
    display_costing(m)
    # ```

# This code:

# 1. Creates a simple flowsheet with a pump unit
# 2. Defines a volumetric flow rate for sizing
# 3. Uses the QGESS costing framework from the UKy flowsheet to cost the pump
# 4. Prints key cost results including the bare erected cost and total installed cost

# The pump costing is based on the volumetric flow rate correlation from the UKy report. The bare erected cost represents the basic equipment cost, while the total installed cost includes additional installation factors.

# You can run this as a standalone example to see how pump costs scale with flow rate. You could also modify the flow rate, number of pumps, or other costing parameters to explore different scenarios.
