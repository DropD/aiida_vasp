"""
Parser manager.

---------------
Manages the parsing and executes the actual parsing by locating which file parsers
to use for each defined quantity.
"""

from aiida_vasp.utils.extended_dicts import DictWithAttributes


class ParserManager(object):  # pylint: disable=useless-object-inheritance
    """
    A manager for FileParsers.

    :param vasp_parser: Reference to the VaspParser required for logging.
    :param quantities: Reference to a ParsableQuantities object for getting quantities.
    :param settings: A dictionary holding the 'parser_settings'.
    """

    def __init__(self, node=None, vasp_parser_logger=None):
        self._node = node
        self._vasp_parser_logger = vasp_parser_logger
        self._quantities_to_parse = []

    @property
    def quantities_to_parse(self):
        return self._quantities_to_parse

    def remove(self, quantity):
        if quantity in self._quantities_to_parse:
            self._quantities_to_parse.remove(quantity)

    def setup(self, quantities_to_parse=None, quantities=None):
        self._set_quantities_to_parse(quantities_to_parse, quantities)

    def _add_quantity_to_parse(self, quantities):
        """Check, whether a quantity or it's alternatives can be added."""
        for quantity in quantities:
            if quantity.is_parsable:
                self._quantities_to_parse.append(quantity.original_name)
                return True
        return False

    def _set_quantities_to_parse(self, quantities_to_parse, quantities):
        """Set the quantities to parse list."""

        self._quantities_to_parse = []
        for quantity_name in quantities_to_parse:
            if not quantities.get_by_name(quantity_name):
                self._vasp_parser_logger.warning('{quantity} has been requested, '
                                                 'however its parser has not been implemented. '
                                                 'Please check the docstrings in aiida_vasp.parsers.vasp.py '
                                                 'for valid input.'.format(quantity=quantity_name))
                continue

            # Add this quantity or one of its alternatives to the quantities to parse.
            success = self._add_quantity_to_parse(quantities.get_equivalent_quantities(quantity_name))

            if not success:
                # Neither the quantity nor it's alternatives could be added to the quantities_to_parse.
                # Gather a list of all the missing files and issue a warning.
                missing_files = quantities.get_missing_files(quantity_name)
                # Check if the missing files are defined in the retrieve list
                retrieve_list = self._node.get_retrieve_temporary_list() + self._node.get_retrieve_list()
                not_in_retrieve_list = None
                for item in missing_files:
                    if item not in retrieve_list:
                        not_in_retrieve_list = item
                self._vasp_parser_logger.warning('The quantity {quantity} has been requested for parsing, however the '
                                                 'following files required for parsing it have not been '
                                                 'retrieved: {missing_files}.'.format(quantity=quantity_name, missing_files=missing_files))
                if not_in_retrieve_list is not None:
                    self._vasp_parser_logger.warning(
                        'The file {not_in_retrieve_list} is not present '
                        'in the list of files to be retrieved. If you want to add additional '
                        'files, please make sure to define it in the ADDITIONAL_RETRIEVE_LIST, '
                        'which is an option given to calculation settings.'.format(not_in_retrieve_list=not_in_retrieve_list))
