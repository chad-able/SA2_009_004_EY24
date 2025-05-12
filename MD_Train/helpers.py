from pyomo.environ import Var, value
import json

def export_variables_to_dict(recovery, model, nf_recovery_fraction=1.0):
    """
    Export all variables from a Pyomo model to a JSON file.
    Works with both scalar and indexed variables.
    """

    # Create a dictionary to hold all variable values
    var_dict = {}

    var_dict['recovery'] = round(recovery, 3) * nf_recovery_fraction

    # Iterate through all variable components
    for v in model.component_objects(Var, active=True):
        if not v.name.startswith('fs.costing'):
            raise TypeError('Expecting a costing block')

        name = v.name.replace('fs.costing.','')
        # Check if it's an indexed variable
        if v.is_indexed():
            # Convert index to string if it's a tuple or other non-string type
            var_dict[name+'_electricity'] = v['electricity'].value
        else:
            # It's a scalar variable
            var_dict[name] = v.value

    # Include the QGESS lcow
    var_dict['lcow'] = round(value(model.QGESS_LCOW), 2)

    return var_dict  # Also return the dictionary in case it's needed

def dump_to_json(data: list, filename: str):
    with open(filename, 'w') as f:
        json.dump(data, f)

