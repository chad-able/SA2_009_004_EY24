from flowsheets import MD_single_stage_continuous_recirculation as MD
import matplotlib.pyplot as plt
import numpy as np

area = 100

#Build the model

m = MD.build()
MD.set_operating_conditions(m)
MD.initialize_system(m)
m.fs.MD.area.fix(area)
MD.solve(m)
m.fs.MD.report()
print(m.fs.costing.total_capital_cost.extract_values())

