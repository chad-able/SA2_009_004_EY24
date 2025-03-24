import pytest
from pyomo.environ import ConcreteModel, value, units as pyunits, assert_optimal_termination
from idaes.core import FlowsheetBlock
from watertap.property_models.multicomp_aq_sol_prop_pack import MCASParameterBlock
from watertap.property_models.seawater_prop_pack import SeawaterParameterBlock
from translator import MCAStoSeawaterTranslator
from idaes.models.unit_models import Product, Feed
from pyomo.network import Arc
from watertap.property_models.tests.test_multicomp_aq_sol_prop_pack import model
from idaes.core.util.scaling import calculate_scaling_factors, get_scaling_factor
from pyomo.util.check_units import assert_units_consistent, assert_units_equivalent
from watertap.core.util.initialization import check_dof
from watertap.core.solvers import get_solver
from idaes.models.unit_models.translator import Translator
import idaes.logger as idaeslog

@pytest.fixture
def setup_input_stream(model):
    m = model

    # Outlet property package
    m.fs.seawater_properties = SeawaterParameterBlock()

    m.fs.translator = MCAStoSeawaterTranslator(
       inlet_property_package = m.fs.properties,
       outlet_property_package = m.fs.seawater_properties
    )

    m.fs.translator.inlet.flow_mol_phase_comp[0.0, "Liq", "A"].fix(0.000407)
    m.fs.translator.inlet.flow_mol_phase_comp[0.0, "Liq", "B"].fix(0.010479)
    m.fs.translator.inlet.flow_mol_phase_comp[0.0, "Liq", "C"].fix(0.010479)
    m.fs.translator.inlet.flow_mol_phase_comp[0.0, "Liq", "D"].fix(0.000407)
    m.fs.translator.inlet.flow_mol_phase_comp[0.0, "Liq", "H2O"].fix(0.99046)
    m.fs.translator.inlet.temperature.fix(298.15)
    m.fs.translator.inlet.pressure.fix(101325)

    calculate_scaling_factors(m.fs)

    assert_units_consistent(m)

    check_dof(m, fail_flag=True)

    m.fs.translator.initialize()

    return m


def test_tds_translation(setup_input_stream):
    m = setup_input_stream

    tds_inlet_flow = value(pyunits.convert(
        m.fs.translator.properties_in[0.0].total_dissolved_solids,
        to_units = pyunits.kg/pyunits.m**3
    )) * value(m.fs.translator.properties_in[0.0].flow_vol_phase["Liq"])

    assert value(m.fs.translator.outlet.flow_mass_phase_comp[0.0, "Liq", "TDS"]) == pytest.approx(
        tds_inlet_flow, rel=1e-3
    )

    assert value(m.fs.translator.properties_out[0.0].pressure) == value(m.fs.translator.properties_in[0.0].pressure)
    assert value(m.fs.translator.properties_out[0.0].temperature) == value(m.fs.translator.properties_in[0.0].temperature) 
