# TODO: Need to run an NF simulation, and the convert the results from the product to be a mass fraction.

import NF_ZO
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

