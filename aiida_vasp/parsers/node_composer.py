"""
Node composer.

--------------
A composer that composes different quantities onto AiiDA data nodes.
"""

from copy import deepcopy
from aiida_vasp.utils.aiida_utils import get_data_class
from aiida_vasp.parsers.quantity import ParsableQuantities

NODES_TYPES = {
    'dict': ['total_energies', 'maximum_force', 'maximum_stress', 'symmetries', 'magnetization', 'site_magnetization', 'notifications'],
    'array.kpoints': ['kpoints'],
    'structure': ['structure'],
    'array.trajectory': ['trajectory'],
    'array.bands': ['eigenvalues', 'kpoints', 'occupancies'],
    'vasp.chargedensity': ['chgcar'],
    'vasp.wavefun': ['wavecar'],
    'array': [],
}


def get_node_composer_inputs(parsable_quantities=None, parsed_quantities=None, file_parser=None, node_type=None, quantity_names=None):
    """Node composer inputs from file parsers"""
    if file_parser is None:
        _parsable_quantities = parsable_quantities
        _parsed_quantities = parsed_quantities
    else:
        _parsable_quantities, _parsed_quantities = _get_quantities_from_file_parser(file_parser)

    return _collect_quantity_data(_parsable_quantities, _parsed_quantities, node_type=node_type, quantity_names=quantity_names)


def _get_quantities_from_file_parser(file_parser):
    """Assemble necessary data from file_parser"""
    parsable_quantities = ParsableQuantities()
    parsed_quantities = {}
    for key, value in file_parser.parsable_items.items():
        parsable_quantities.add_parsable_quantity(key, deepcopy(value))
        parsed_quantities[key] = file_parser.get_quantity(key)
    return parsable_quantities, parsed_quantities


def _collect_quantity_data(parsable_quantities, parsed_quantities, node_type=None, quantity_names=None):
    """Collect data into inputs"""
    if quantity_names is None:
        _quantity_names = NODES_TYPES.get(node_type)
    else:
        _quantity_names = quantity_names

    inputs = {}
    for quantity_name in _quantity_names:
        quantity = parsable_quantities.get_by_name(quantity_name)
        parsed_quantity = parsed_quantities.get(quantity_name)
        if parsed_quantity is None:
            inputs.update(_get_alternative_parsed_quantity(quantity_name, quantity, parsable_quantities, parsed_quantities))
        else:
            inputs[quantity.name] = parsed_quantity

    return inputs


def _get_alternative_parsed_quantity(quantity_name, quantity, parsable_quantities, parsed_quantities):
    """Return alternative quantities"""
    inputs = {}
    for parsable_quantity in parsable_quantities.get_equivalent_quantities(quantity_name):
        original_name = parsable_quantity.original_name
        if original_name in parsed_quantities:
            inputs[quantity.name] = parsed_quantities.get(original_name)
    return inputs


class NodeComposer:
    """
    Prototype for a generic NodeComposer, that will compose output nodes based on parsed quantities.

    Provides methods to compose output_nodes from quantities. Currently supported node types are defined in NODES_TYPES.
    """

    @classmethod
    def compose(cls, node_type, inputs):
        """
        A wrapper for compose_node with a node definition taken from NODES.

        :param node_type: str holding the type of the node. Must be one of the keys of NODES_TYPES.
        :param quantities: A list of strings with quantities to be used for composing this node.

        :return: An AiidaData object of a type corresponding to node_type.
        """

        # Call the correct specialised method for assembling.
        return getattr(cls, '_compose_' + node_type.replace('.', '_'))(node_type, inputs)

    @staticmethod
    def _compose_dict(node_type, inputs):
        """Compose the dictionary node."""
        node = get_data_class(node_type)()
        node.update_dict(inputs)
        return node

    @staticmethod
    def _compose_structure(node_type, inputs):
        """Compose a structure node."""
        node = get_data_class(node_type)()
        for key in inputs:
            node.set_cell(inputs[key]['unitcell'])
            for site in inputs[key]['sites']:
                node.append_atom(position=site['position'], symbols=site['symbol'], name=site['kind_name'])
        return node

    @staticmethod
    def _compose_array(node_type, inputs):
        """Compose an array node."""
        node = get_data_class(node_type)()
        for item in inputs:
            for key, value in inputs[item].items():
                node.set_array(key, value)
        return node

    @staticmethod
    def _compose_vasp_wavefun(node_type, inputs):
        """Compose a wave function node."""
        node = None
        for key in inputs:
            # Technically this dictionary has only one key. to
            # avoid problems with python 2/3 it is done with the loop.
            node = get_data_class(node_type)(file=inputs[key])
        return node

    @staticmethod
    def _compose_vasp_chargedensity(node_type, inputs):
        """Compose a charge density node."""
        node = None
        for key in inputs:
            # Technically this dictionary has only one key. to
            # avoid problems with python 2/3 it is done with the loop.
            node = get_data_class(node_type)(file=inputs[key])
        return node

    @classmethod
    def _compose_array_bands(cls, node_type, inputs):
        """Compose a bands node."""
        node = get_data_class(node_type)()
        kpoints = cls._compose_array_kpoints('array.kpoints', {'kpoints': inputs['kpoints']})
        node.set_kpointsdata(kpoints)
        node.set_bands(inputs['eigenvalues'], occupations=inputs['occupancies'])
        return node

    @staticmethod
    def _compose_array_kpoints(node_type, inputs):
        """Compose an array.kpoints node based on inputs."""
        node = get_data_class(node_type)()
        for key in inputs:
            mode = inputs[key]['mode']
            if mode == 'explicit':
                kpoints = inputs[key].get('points')
                cartesian = not kpoints[0].get_direct()
                kpoint_list = []
                weights = []
                for kpoint in kpoints:
                    kpoint_list.append(kpoint.get_point().tolist())
                    weights.append(kpoint.get_weight())

                if weights[0] is None:
                    weights = None

                node.set_kpoints(kpoint_list, weights=weights, cartesian=cartesian)

            if mode == 'automatic':
                mesh = inputs[key].get('divisions')
                shifts = inputs[key].get('shifts')
                node.set_kpoints_mesh(mesh, offset=shifts)
        return node

    @staticmethod
    def _compose_array_trajectory(node_type, inputs):
        """
        Compose a trajectory node.

        Parameters
        ----------
        node_type : str
            'array.trajectory'
        inputs : dict
            trajectory data is stored at VasprunParser. The keys are
            'cells', 'positions', 'symbols', 'forces', 'stress', 'steps'.

        Returns
        -------
        node : TrajectoryData
            To store the data, due to the definition of TrajectoryData in
            aiida-core v1.0.0, data, using the same keys are those from inputs,
            for 'symbols', the value is stored by set_attribute and
            for the others, the values are stored by by set_array.

        """
        node = get_data_class(node_type)()
        for item in inputs:
            for key, value in inputs[item].items():
                if key == 'symbols':
                    node.set_attribute(key, value)
                else:
                    node.set_array(key, value)
        return node
