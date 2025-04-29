from pyomo.environ import (
    ConcreteModel,
    value,
    Constraint,
    Objective,
    Var,
    Expression,
    TransformationFactory,
    units as pyunits,
    check_optimal_termination,
    assert_optimal_termination,
)
from pyomo.environ import units



def QGESS_costing(m, units, liq_waste=0, sol_waste=0, water_flow_rate=0, **cost_params):
    # Function which calculates all associated cost parameters based on the PrOMMiS QGESS method
    # Calculates the LCOW and all other cost parameters (separated into individual functions)
    # Returns the model used (the model will now include all associated parameters)
    # Requires the model, the equipment (units) and any cost parameters to replace defaults below
    # If desired, can handle costs for liquid waste and solid waste (default set to False)
    # liquid waste flow rate in m3/hr
    # solid waste flow rate in ton/yr
    # water flow rate (necessary for LCOW) in m3/hr

    cost_parameters = {
        # capital cost parameters
        'BEC_factor': 1.58,
        'piping_materials_and_labor_percentage': 20,
        'electrical_materials_and_labor_percentage': 20,
        'instrumentation_percentage': 8,
        'plants_services_percentage': 10,
        'process_buildings_percentage': 40,
        'auxiliary_buildings_percentage': 15,
        'site_improvements_percentage': 10,
        'equipment_installation_percentage': 17,
        'field_expenses_percentage': 12,
        'project_management_and_construction_percentage': 30,
        'process_contingency_percentage': 15,
        'TASC_TOC_Factor': 1.207,
        'CRF': 0.0769,
        # operating cost parameters
        'labor_types': [
            "skilled",
            "unskilled",
            "supervisor",
            "maintenance",
            "technician",
            "engineer",
        ],
        'labor_rate': [26.08, 19.08, 30.39, 22.73, 21.97, 45.85],  # USD/hr
        'labor_burden': 25,  # % fringe benefits
        'operators_per_shift': [2, 0, 0, 0, 0, 0],
        'hours_per_shift': 8,
        'shifts_per_day': 3,
        'operating_days_per_year': 365,
        'maintenance_material_percentage': 2,
        'QAQC_percentage': 10,
        'administrative_labor_percentage': 20,
        'property_tax_and_insurance_percentage': 1,

        # waste parameters
        'has_liquid_waste': False,
        'liq_waste_disposal_cost': 1.5, # $/bbl
        'has_solid_waste': False,
        'sol_waste_disposal_cost': 1, # $/ton
        'electricity_cost': 8.09/100,

        # Product and efficiency parameters (currently not used)
        'mixed_product_sale_price_realization_factor': 0.65,
        'efficiency': 0.80,  # power usage efficiency
        'resources': [],
        'rates': [],
        # former O&M cost parameters from base method (currently not used)
        'fixed_OM': True,
        'variable_OM': True,
        'land_cost': 1,
        # 'cost_units': units.USD_2018
    }

    for key, value in cost_params.items():
        if key in cost_parameters:
            cost_parameters[key] = value

    total_equip_cost = 0
    for unit in units:
        total_equip_cost = total_equip_cost + unit.costing.capital_cost

    m.fs.costing.total_equip_cost = total_equip_cost
    m.fs.costing.electricity_cost.fix(cost_parameters['electricity_cost'])
    m = QGESS_cap_cost(m, **cost_parameters)
    m = QGESS_op_cost(m, liq_waste, sol_waste, **cost_parameters)

    m.fs.costing.QGESS_annualized_cost = Expression(expr=(m.fs.costing.QGESS_annualized_capital_cost+m.fs.costing.QGESS_fixed_operating_cost+m.fs.costing.QGESS_variable_operating_cost))

    m.fs.costing.QGESS_LCOW = Expression(expr=(m.fs.costing.QGESS_annualized_cost/
                                             (water_flow_rate*24*cost_parameters['operating_days_per_year'])))

    return m

def QGESS_cap_cost(m, **cost_params):

    cost_parameters = {
        # capital cost parameters
        'BEC_factor': 1.58,
        'piping_materials_and_labor_percentage': 20,
        'electrical_materials_and_labor_percentage': 20,
        'instrumentation_percentage': 8,
        'plants_services_percentage': 10,
        'process_buildings_percentage': 40,
        'auxiliary_buildings_percentage': 15,
        'site_improvements_percentage': 10,
        'equipment_installation_percentage': 17,
        'field_expenses_percentage': 12,
        'project_management_and_construction_percentage': 30,
        'process_contingency_percentage': 15,
        'TASC_TOC_Factor': 1.207,
        'CRF': 0.0769,
    }

    for key, value in cost_params.items():
        if key in cost_parameters:
            cost_parameters[key] = value

        # Calculate BEC

    m.fs.costing.total_BEC = Expression(expr=m.fs.costing.total_equip_cost * cost_parameters['BEC_factor'] * units.USD_2023)

    # Calculate ancillary costs
    m.fs.costing.piping_MandL = Expression(expr=m.fs.costing.total_BEC * cost_parameters['piping_materials_and_labor_percentage']/100)
    m.fs.costing.elec_MandL = Expression(expr=m.fs.costing.total_BEC * cost_parameters['electrical_materials_and_labor_percentage']/100)
    m.fs.costing.instrument = Expression(expr=m.fs.costing.total_BEC * cost_parameters['instrumentation_percentage']/100)
    m.fs.costing.plant_serv = Expression(expr=m.fs.costing.total_BEC * cost_parameters['piping_materials_and_labor_percentage']/100)

    m.fs.costing.ancillary_cost = Expression(
        expr=(m.fs.costing.piping_MandL + m.fs.costing.elec_MandL + m.fs.costing.instrument + m.fs.costing.plant_serv))

    # calculate building costs
    m.fs.costing.proc_build = Expression(expr=m.fs.costing.total_BEC * cost_parameters['process_buildings_percentage']/100)
    m.fs.costing.aux_build = Expression(expr=m.fs.costing.total_BEC * cost_parameters['auxiliary_buildings_percentage']/100)
    m.fs.costing.sic_build = Expression(expr=m.fs.costing.total_BEC * cost_parameters['site_improvements_percentage']/100)

    m.fs.costing.building_cost = Expression(
        expr=(m.fs.costing.proc_build + m.fs.costing.aux_build + m.fs.costing.sic_build))

    # calculate EPCM costs
    m.fs.costing.eic = Expression(expr=m.fs.costing.total_BEC * cost_parameters['equipment_installation_percentage']/100)
    m.fs.costing.fec = Expression(expr=m.fs.costing.total_BEC * cost_parameters['field_expenses_percentage']/100)
    m.fs.costing.pmcc = Expression(expr=m.fs.costing.total_BEC * cost_parameters['project_management_and_construction_percentage']/100)

    m.fs.costing.epcm_cost = Expression(expr=(m.fs.costing.eic + m.fs.costing.fec + m.fs.costing.pmcc))

    # Contingency costs
    m.fs.costing.contingency_cost = Expression(expr=(cost_parameters['process_contingency_percentage']/100 * m.fs.costing.total_BEC))

    # Total installed costs
    m.fs.costing.TIC_cost = Expression(expr=(
                m.fs.costing.ancillary_cost + m.fs.costing.building_cost + m.fs.costing.epcm_cost + m.fs.costing.contingency_cost))

    # Total plant costs, total overnight cost
    m.fs.costing.TPC_cost = Expression(expr=(m.fs.costing.total_BEC + m.fs.costing.TIC_cost))
    m.fs.costing.TOC_cost = Expression(expr=(m.fs.costing.TPC_cost))

    # TASC and annualized capital costs

    m.fs.costing.TASC_cost = Expression(expr=(cost_parameters['TASC_TOC_Factor'] * m.fs.costing.TOC_cost))
    m.fs.costing.QGESS_annualized_capital_cost = Expression(expr=(cost_parameters['CRF'] * m.fs.costing.TASC_cost))

    return m

def QGESS_op_cost(m, liq_waste, sol_waste, **cost_params):

    cost_parameters = {
        # operating cost parameters
        'labor_types': [
            "skilled",
            "unskilled",
            "supervisor",
            "maintenance",
            "technician",
            "engineer",
        ],
        'labor_rate': [26.08, 19.08, 30.39, 22.73, 21.97, 45.85],  # USD/hr
        'labor_burden': 25,  # % fringe benefits
        'operators_per_shift': [2, 0, 0, 0, 0, 0],
        'hours_per_shift': 8,
        'shifts_per_day': 3,
        'operating_days_per_year': 365,
        'maintenance_material_percentage': 2,
        'QAQC_percentage': 10,
        'administrative_labor_percentage': 20,
        'property_tax_and_insurance_percentage': 1,

        # waste parameters
        'has_liquid_waste': False,
        'liq_waste_disposal_cost': 1.5, # $/bbl
        'has_solid_waste': False,
        'sol_waste_disposal_cost': 1, # $/ton
        'electricity_cost': 8.09 / 100,

        # Product and efficiency parameters (currently not used)
        'mixed_product_sale_price_realization_factor': 0.65,
        'efficiency': 0.80,  # power usage efficiency
        'resources': [],
        'rates': [],
        # former O&M cost parameters from base method (currently not used)
        'fixed_OM': True,
        'variable_OM': True,
        'land_cost': 1,
        # 'cost_units': units.USD_2018,
    }

    for key, value in cost_params.items():
        if key in cost_parameters:
            cost_parameters[key] = value

    for i in range(len(cost_parameters['labor_rate'])):
        m.fs.costing.QGESS_operating_labor_cost = Expression(expr=(cost_parameters['labor_rate'][i]*cost_parameters['operators_per_shift'][i]*(1+cost_parameters['labor_burden']/100)*cost_parameters['hours_per_shift']*
                                                                   cost_parameters['shifts_per_day']*cost_parameters['operating_days_per_year']*units.USD_2023))

    #maintenance and material costs
    m.fs.costing.MM_cost = Expression(expr=cost_parameters['maintenance_material_percentage']/100*m.fs.costing.TPC_cost)

    #QAQC costs
    m.fs.costing.QAQC_cost = Expression(expr=cost_parameters['QAQC_percentage']/100*m.fs.costing.QGESS_operating_labor_cost)

    #Admin labor costs
    m.fs.costing.Admin_labor_cost = Expression(expr=cost_parameters['administrative_labor_percentage']/100*m.fs.costing.QGESS_operating_labor_cost)

    #Patent costs are ignored (no sales yet)
    #Property taxes

    m.fs.costing.prop_tax_insurance_cost = Expression(expr=cost_parameters['property_tax_and_insurance_percentage']/100*m.fs.costing.TPC_cost)

    #WaterTAP costs are included here for fixed operating costs
    #For this flowsheet, only membrane replacement is needed


    #Summing relevant costs
    m.fs.costing.QGESS_fixed_operating_cost = Expression(expr=(m.fs.costing.QGESS_operating_labor_cost+m.fs.costing.MM_cost+m.fs.costing.QAQC_cost+m.fs.costing.Admin_labor_cost+m.fs.costing.prop_tax_insurance_cost))

    #Variable operating costs
    #land costs are set to 0

    #Per resource (waste disposal, antiscalant, electricity)
    #Note that solid masses are taken from OLI (not calculated in WaterTAP)
    m.fs.costing.VOP_resource_cost = Expression(
        expr=(m.fs.costing.aggregate_flow_costs["electricity"] * cost_parameters['operating_days_per_year'] / 365))
    # m.fs.costing.VOP_resource_cost = 0

    if cost_parameters['has_liquid_waste']:
        m.fs.costing.liquid_waste_resource_cost = Expression(expr=(liq_waste*264.172/42*24*cost_parameters['operating_days_per_year'] / 365*cost_parameters['liq_waste_disposal_cost']*units.USD_2023))
        m.fs.costing.VOP_resource_cost = m.fs.costing.VOP_resource_cost + m.fs.costing.liquid_waste_resource_cost

    if cost_parameters['has_solid_waste']:
        m.fs.costing.solid_waste_resource_cost = Expression(expr=sol_waste*cost_parameters['sol_waste_disposal_cost']*units.USD_2023)
        m.fs.costing.VOP_resource_cost = m.fs.costing.VOP_resource_cost + m.fs.costing.solid_waste_resource_cost

    m.fs.costing.plant_overhead_cost = Expression(expr=(0.2*(m.fs.costing.QGESS_fixed_operating_cost+m.fs.costing.VOP_resource_cost)))

    m.fs.costing.QGESS_variable_operating_cost = Expression(expr=(m.fs.costing.VOP_resource_cost+m.fs.costing.plant_overhead_cost))

    return m