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
import pandas as pd


m = ConcreteModel()
m.fs = FlowsheetBlock(dynamic=False)

# --------------------------- NANOFILTRATION ---------------------------
# TODO: switch to qgess
m.fs.costing = WaterTAPCosting()
NF_ZO.build(m)
NF_ZO.costing(m)
NF_ZO.display_summary(m)

stream_dict = arcs_to_stream_dict(m)
stream_df = create_stream_table_dataframe(stream_dict)
stream_df.columns = ['Units', 'Feed Inlet', 'Feed Inlet', 'Permeate Outlet', 'Feed Outlet']

### Calculate the mass fraction of each species

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

### Assume that the TDS recovery rate is 97 %
permeate_fraction = 1-0.97
tds_mass_flow = 0.101336 * 100 # kg/s, 100 is water flowrate
tds_permeate_mass = tds_mass_flow * permeate_fraction
tds_retentate_mass = tds_mass_flow * 0.97

tds_row = ['kilogram / second', tds_mass_flow, tds_mass_flow, tds_permeate_mass, tds_retentate_mass]
temp_idx = stream_df.index.get_loc('temperature')
stream_df = pd.concat([
    stream_df.iloc[:temp_idx],
    pd.DataFrame([tds_row], columns=stream_df.columns, index=["flow_mass_phase_comp ('Liq', 'TDS')"]),
    stream_df.iloc[temp_idx:]
])
print(stream_df)

# Calculate mass fractions
mass_fractions_df = calculate_mass_fractions(stream_df)

# The total dissolved solids is 1-x_h2O. This is the input for OARO. 
tds = mass_fractions_df.loc['H2O']['Feed Outlet']

