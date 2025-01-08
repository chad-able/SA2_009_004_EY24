# TODO: Need to run an NF simulation, and the convert the results from the product to be a mass fraction.

import NF_ZO
import inspect
import pprint
from idaes.core.util.tables import create_stream_table_dataframe, arcs_to_stream_dict

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
import inspect
from pyomo.network import Arc
from idaes.core import FlowsheetBlock
from watertap.costing import WaterTAPCosting

m = ConcreteModel()
m.fs = FlowsheetBlock(dynamic=False)

# TODO: switch to qgess
m.fs.costing = WaterTAPCosting()
NF_ZO.build(m)
NF_ZO.costing(m)
NF_ZO.display_summary(m)

stream_dict = arcs_to_stream_dict(m)
stream_df = create_stream_table_dataframe(stream_dict)
stream_df.columns = ['Units', 'Feed Inlet', 'Feed Inlet', 'Permeate Outlet', 'Feed Outlet']

def calculate_mass_fractions(stream_df):
    # Get the flow rows only (excluding temperature and pressure)
    flow_rows = stream_df[stream_df.index.str.contains('flow_mass_phase_comp')]
    
    # Calculate total mass flow for each stream
    total_flows = flow_rows.iloc[:, 1:].sum()
    
    # Create mass fraction dataframe
    mass_frac_df = flow_rows.iloc[:, 1:].div(total_flows, axis=1)
    
    # Clean up index names to show only component names
    mass_frac_df.index = flow_rows.index.str.extract(r"'Liq', '(.+)'").iloc[:, 0]
    
    # Add units column
    mass_frac_df.insert(0, 'Units', 'kg/kg')
    
    return mass_frac_df

# Calculate and display mass fractions
mass_fractions_df = calculate_mass_fractions(stream_df)
print("\nMass Fractions:")
print(mass_fractions_df)
