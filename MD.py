from watertap.flowsheets.MD import MD_single_stage_continuous_recirculation as MD
import matplotlib.pyplot as plt
import numpy as np
data = {
    "Cold Out": [],
    "Hot Out": [],
}
#Build the model
for area in np.linspace(30, 100, 10):
    m = MD.build()
    MD.set_operating_conditions(m)
    MD.initialize_system(m)
    m.fs.MD.area.fix(area)
    MD.solve(m)
    m.fs.MD.report()

    hot_total = m.fs.MD.hot_ch_outlet.flow_mass_phase_comp[0, "Liq", "H2O"].value + m.fs.MD.hot_ch_outlet.flow_mass_phase_comp[0, "Liq", "H2O"].value

    data["Cold Out"].append(m.fs.MD.cold_ch_outlet.flow_mass_phase_comp[0, "Liq", "H2O"].value)
    data["Hot Out"].append(m.fs.MD.hot_ch_outlet.flow_mass_phase_comp[0, "Liq", "H2O"].value/hot_total)

#plt.plot(np.linspace(30, 100, 10), data["Cold Out"], 'bo')
plt.plot(np.linspace(30, 100, 10), data["Hot Out"], 'ro')

plt.show()

# m = MD.build()
# MD.set_operating_conditions(m)
# MD.initialize_system(m)
# m.fs.MD.area.fix(100)
# MD.solve(m)
# m.fs.MD.report()
