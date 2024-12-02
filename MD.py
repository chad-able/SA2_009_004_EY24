from pyomo.environ import value
from flowsheets import MD_single_stage_continuous_recirculation as MD
import matplotlib.pyplot as plt
import numpy as np
from idaes.core.util.tables import arcs_to_stream_dict, create_stream_table_dataframe
import pandas as pd
import time
import sys

area = 100

#Build the model

# Create a plot with 3 columns and 1 row
fig, ax = plt.subplots(1, 3, figsize=(15, 5))

membrane_coeff = np.arange(15,25,2)
recovery = np.arange(0.4,0.8,0.1)

color_cycle = plt.rcParams['axes.prop_cycle'].by_key()['color']

for rec, color in zip(recovery, color_cycle):
    lcow = []
    sec = []
    for num in membrane_coeff:
        m = MD.build()
        MD.set_operating_conditions(m, recovery=rec, recycle_coeff=num)
        MD.initialize_system(m)
        MD.solve(m)
        lcow.append(value(m.fs.costing.LCOW))
        sec.append(value(m.fs.costing.specific_energy_consumption))
        m.fs.costing.LCOW.display()

    # Plot index vs lcow in the first plot
    ax[0].scatter(membrane_coeff, lcow, color=color)
    ax[1].scatter(membrane_coeff, sec, color=color)
    ax[2].scatter(sec, lcow)

plt.show()


# Get feed volumetric flowrate
#feed_flow = m.fs.feed.properties[0].flow_vol_phase["Liq"].value


# m.fs.visualize("Flowsheet")
# try:
#     print("Type ^C to stop the program")
#     while True:
#         time.sleep(1)
# except KeyboardInterrupt:
#     print("Program stopped")
