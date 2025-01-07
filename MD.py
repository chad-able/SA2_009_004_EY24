from numpy._typing import _256Bit
from pyomo.environ import value
from flowsheets import MD_single_stage_continuous_recirculation as MD
import matplotlib.pyplot as plt
import numpy as np
from idaes.core.util.tables import arcs_to_stream_dict, create_stream_table_dataframe
import pandas as pd
import time
import sys


membrane_coeff = 7
recovery = 0.5

m = MD.build()

# This is where the parameters you need to change are
MD.set_operating_conditions(m, recovery=recovery, recycle_coeff=membrane_coeff)

MD.initialize_system(m)
MD.solve(m)
MD.display_system(m)

lcow = value(m.fs.costing.LCOW)
sec = value(m.fs.costing.specific_energy_consumption)
area = m.fs.MD.area.value


# Get feed volumetric flowrate
#feed_flow = m.fs.feed.properties[0].flow_vol_phase["Liq"].value


# m.fs.visualize("Flowsheet")
# try:
#     print("Type ^C to stop the program")
#     while True:
#         time.sleep(1)
# except KeyboardInterrupt:
#     print("Program stopped")
