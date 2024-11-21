from flowsheets import MD_single_stage_continuous_recirculation as MD
import matplotlib.pyplot as plt
import numpy as np
from idaes.core.util.tables import arcs_to_stream_dict, create_stream_table_dataframe
import pandas as pd

area = 100

#Build the model

m = MD.build()
MD.set_operating_conditions(m)
MD.initialize_system(m)
m.fs.MD.area.fix(area)
MD.solve(m)
m.fs.MD.report()

from pprint import pprint
j= create_stream_table_dataframe(arcs_to_stream_dict(m))

# Get feed volumetric flowrate
feed_flow = m.fs.feed.properties[0].flow_vol_phase["Liq"].value
print(feed_flow)

