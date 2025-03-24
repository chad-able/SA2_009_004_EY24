from pyomo.environ import Constraint, units as pyunits, check_optimal_termination, Set, value
import idaes.logger as idaeslog
from watertap.core.solvers import get_solver

from idaes.core import declare_process_block_class
from idaes.models.unit_models.translator import TranslatorData
from idaes.core.util.model_statistics import degrees_of_freedom
from idaes.core.util.exceptions import InitializationError

@declare_process_block_class("MCAStoSeawaterTranslator")
class MCAStoSeawaterTranslatorData(TranslatorData):
    """
    Translator block to convert from MCAS property model to Seawater property model
    """

    def build(self):
        """
        Build translator block
        """
        super(MCAStoSeawaterTranslatorData, self).build()

        @self.Constraint([0])
        def isothermal_eq(blk,t):
            return blk.inlet.temperature[t] == blk.outlet.temperature[t]

        @self.Constraint([0])
        def isobaric_eq(blk,t):
            return blk.inlet.pressure[t] == blk.outlet.pressure[t]

        @self.Constraint([0])
        def isometric_eq(blk,t):
            return blk.properties_in[t].flow_vol_phase["Liq"] == blk.properties_out[t].flow_vol_phase["Liq"] 

        @self.Constraint([0])
        def TDS_eq(blk,t):
            return pyunits.convert(blk.properties_in[t].total_dissolved_solids, to_units=pyunits.kg/pyunits.m**3) == blk.properties_out[t].conc_mass_phase_comp["Liq", "TDS"]

