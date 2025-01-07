from numpy._typing import _256Bit
from pyomo.environ import value
from flowsheets import MD_single_stage_continuous_recirculation as MD
import matplotlib.pyplot as plt
import numpy as np
from idaes.core.util.tables import arcs_to_stream_dict, create_stream_table_dataframe
import pandas as pd
import time
import sys

area = 100
plt.rcParams.update({'font.size': 14})

# Create a plot with 3 columns and 1 row
fig, ax = plt.subplots(1, 3, figsize=(15, 5))

membrane_coeff = np.arange(5,10,1)
recovery = np.arange(0.4,0.8,0.2)

color_cycle = plt.rcParams['axes.prop_cycle'].by_key()['color']

for rec, color in zip(recovery, color_cycle):
    lcow = []
    sec = []
    membrane_area = []
    for num in membrane_coeff:
        m = MD.build()
        MD.set_operating_conditions(m, recovery=rec, recycle_coeff=num)
        MD.initialize_system(m)
        MD.solve(m)
        lcow.append(value(m.fs.costing.LCOW))
        sec.append(value(m.fs.costing.specific_energy_consumption))
        membrane_area.append(m.fs.MD.area.value)

    # Plot index vs lcow in the first plot
    ax[0].scatter(membrane_area, lcow, color=color, label='Fractional recovery: {:.1f}'.format(rec))
    ax[0].set_ylabel('Levelized Cost of Water (\$/m$^3$ water)')
    ax[0].set_xlabel('Membrane Area (m$^2$)')
    ax[1].scatter(membrane_area, sec, color=color, label='Fractional recovery: {:.1f}'.format(rec))
    ax[1].set_ylabel('Specific Energy Consumption (kWh/m$^3$ water)')
    ax[1].set_xlabel('Membrane Area (m$^2$)')
    ax[2].scatter(sec, lcow, label='Fractional recovery: {:.1f}'.format(rec))
    ax[2].set_xlabel('Specific Energy Consumption (kWh/m$^3$ water)')
    ax[2].set_ylabel('Levelized Cost of Water (\$/m$^3$ water)')

ax[0].legend()
ax[1].legend()
ax[2].legend()

plt.tight_layout()
plt.savefig('seclcow.png', dpi=300)
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
