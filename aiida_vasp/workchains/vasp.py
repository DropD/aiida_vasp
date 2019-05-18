"""
Base WorkChain for VASP, Error Handling enriched wrapper around VaspCalculation.

Intended to be reused (launched instead of a VaspCalculation) in all other VASP workchains.
Any validation and / or error handling that applies to *every* VASP run,
should be handled on this level, so that every workchain can profit from it.
Anything related to a subset of use cases must be handled in a subclass.
"""
from aiida.engine import while_
from aiida.common.lang import override
#from aiida.engine.job_processes import override
from aiida.common.extendeddicts import AttributeDict
from aiida.common.exceptions import NotExistent
from aiida.plugins import CalculationFactory
from aiida.orm import Code

from aiida_vasp.utils.aiida_utils import get_data_class, get_data_node
from aiida_vasp.workchains.restart import BaseRestartWorkChain


class VaspWorkChain(BaseRestartWorkChain):
    """
    Error handling enriched wrapper around VaspCalculation.

    Deliberately conserves most of the interface (required inputs) of the VaspCalculation class.

    This is intended to be used instead of directly submitting a VaspCalculation, so that future features like
    automatic restarting, error checking etc. can be propagated to higher level workchains automatically by implementing them here.

    Usage::

        from aiida.common.extendeddicts import AttributeDict
        from aiida.work import submit
        basevasp = WorkflowFactory('vasp.base')
        inputs = basevasp.get_inputs_template  ## AiiDA < 1.0.0a1
        inputs = basevasp.get_builder() ## AiiDA >= 1.0.0a1
        inputs = AttributeDict()  ## all versions (no tab-completion)
        ## ... set inputs (documented at aiida.readthedocs.io)
        submit(basevasp, **inputs)

    To see working examples, including generation of input nodes from scratch, please refer to ``examples/run_base_wf.py``
    and ``examples/run_vasp.py``.
    """
    _verbose = False
    _calculation = CalculationFactory('vasp.vasp')

    @classmethod
    def define(cls, spec):
        super(VaspWorkChain, cls).define(spec)
        spec.input('code', valid_type=Code)
        spec.input('structure', valid_type=(get_data_class('structure'), get_data_class('cif')), required=True)
        spec.input('kpoints', valid_type=get_data_class('array.kpoints'), required=True)
        spec.input('potential_family', valid_type=get_data_class('str'), required=True)
        spec.input('potential_mapping', valid_type=get_data_class('dict'), required=True)
        spec.input('parameters', valid_type=get_data_class('dict'), required=True)
        spec.input('options', valid_type=get_data_class('dict'), required=True)
        spec.input('settings', valid_type=get_data_class('dict'), required=False)
        spec.input('wavecar', valid_type=get_data_class('vasp.wavefun'), required=False)
        spec.input('chgcar', valid_type=get_data_class('vasp.chargedensity'), required=False)
        spec.input(
            'max_iterations',
            valid_type=get_data_class('int'),
            required=False,
            default=get_data_node('int', 5),
            help="""
            The maximum number of iterations to perform.
            """)
        spec.input(
            'clean_workdir',
            valid_type=get_data_class('bool'),
            required=False,
            default=get_data_node('bool', True),
            help="""
            If True, clean the work dir upon the completion of a successfull calculation.
            """)
        spec.input(
            'verbose',
            valid_type=get_data_class('bool'),
            required=False,
            default=get_data_node('bool', False),
            help="""
            If True, enable more detailed output during workchain execution.
            """)

        spec.outline(
            cls.init_context,
            cls.init_inputs,
            while_(cls.run_calculations)(
                cls.init_calculation,
                cls.run_calculation,
                cls.verify_calculation
            ),
            cls.results,
            cls.finalize
        )  # yapf: disable

        spec.output('output_parameters', valid_type=get_data_class('dict'))
        spec.output('remote_folder', valid_type=get_data_class('remote'))
        spec.output('retrieved', valid_type=get_data_class('folder'))
        spec.output('output_structure', valid_type=get_data_class('structure'), required=False)
        spec.output('output_kpoints', valid_type=get_data_class('array.kpoints'), required=False)
        spec.output('output_trajectory', valid_type=get_data_class('array.trajectory'), required=False)
        spec.output('output_chgcar', valid_type=get_data_class('vasp.chargedensity'), required=False)
        spec.output('output_wavecar', valid_type=get_data_class('vasp.wavefun'), required=False)
        spec.output('output_bands', valid_type=get_data_class('array.bands'), required=False)
        spec.output('output_forces', valid_type=get_data_class('array'), required=False)
        spec.output('output_stress', valid_type=get_data_class('array'), required=False)
        spec.output('output_dos', valid_type=get_data_class('array'), required=False)
        spec.output('output_occupancies', valid_type=get_data_class('array'), required=False)
        spec.output('output_energies', valid_type=get_data_class('array'), required=False)
        spec.output('output_projectors', valid_type=get_data_class('array'), required=False)
        spec.output('output_dielectrics', valid_type=get_data_class('array'), required=False)
        spec.output('output_born_charges', valid_type=get_data_class('array'), required=False)
        spec.output('output_hessian', valid_type=get_data_class('array'), required=False)
        spec.output('output_dynmat', valid_type=get_data_class('array'), required=False)

    def init_calculation(self):
        """Set the restart folder and set parameters tags for a restart."""
        if isinstance(self.ctx.restart_calc, self._calculation):
            self.ctx.inputs.restart_folder = self.ctx.restart_calc.outputs.remote_folder
            old_parameters = AttributeDict(self.ctx.inputs.parameters.get_dict())
            parameters = old_parameters.copy()
            if 'istart' in parameters:
                parameters.istart = 1
            if 'icharg' in parameters:
                parameters.icharg = 1
            if parameters != old_parameters:
                self.ctx.inputs.parameters = get_data_node('dict', dict=parameters)

    def init_inputs(self):
        """Make sure all the required inputs are there and valid, create input dictionary for calculation."""
        self.ctx.inputs = AttributeDict()

        # Set the code
        self.ctx.inputs.code = self.inputs.code

        # Set the structure (poscar)
        self.ctx.inputs.structure = self.inputs.structure

        # Set the kpoints (kpoints)
        self.ctx.inputs.kpoints = self.inputs.kpoints

        # Set the parameters (incar)
        self.ctx.inputs.parameters = self.inputs.parameters

        # Set settings
        if 'settings' in self.inputs:
            self.ctx.inputs.settings = self.inputs.settings
            
        # Set options
        # Options is very special, not storable and should be
        # wrapped in the metadata dictionary, which is also not storable
        # and should contain an entry for options
        if 'options' in self.inputs:
            options = {}
            options.update(self.inputs.options)
            self.ctx.inputs.metadata = {}
            self.ctx.inputs.metadata['options'] = options
            # Also make sure we specify the entry point for the
            # default parser if that is not already specified
            default_parser = self.ctx.inputs.metadata['options'].get('parser_name', 'vasp.vasp')
            self.ctx.inputs.metadata['options']['parser_name'] = default_parser

        # Verify and set potentials (potcar)
        if not self.inputs.potential_family.value:
            self.report('An empty string for the potential family name was detected.')
            return 1
        try:
            self.ctx.inputs.potential = get_data_class('vasp.potcar').get_potcars_from_structure(
                structure=self.inputs.structure,
                family_name=self.inputs.potential_family.value,
                mapping=self.inputs.potential_mapping.get_dict())
        except ValueError as err:
            self.exit_status = 1
            self.exit_message = err
            return
        except NotExistent as err:
            self.exit_status = 1
            self.exit_message = err
            return
        try:
            self._verbose = self.inputs.verbose.value
        except AttributeError:
            pass
        # Set the charge density (chgcar)
        if 'chgcar' in self.inputs:
            self.ctx.inputs.charge_density = self.inputs.chgcar

        # Set the wave functions (wavecar)
        if 'wavecar' in self.inputs:
            self.ctx.inputs.wavefunctions = self.inputs.wavecar

    @override
    def on_except(self, exc_info):
        """Handle excepted state."""
        try:
            last_calc = self.ctx.calculations[-1] if self.ctx.calculations else None
            if last_calc is not None:
                self.report('Last calculation: {calc}'.format(calc=repr(last_calc)))
                sched_err = last_calc.outputs.retrieved.get_file_content('_scheduler-stderr.txt')
                sched_out = last_calc.outputs.retrieved.get_file_content('_scheduler-stdout.txt')
                self.report('Scheduler output:\n{}'.format(sched_out or ''))
                self.report('Scheduler stderr:\n{}'.format(sched_err or ''))
        except AttributeError:
            self.report('No calculation was found in the context. ' 'Something really awefull happened. Please inspect messages and act.')

        return super(VaspWorkChain, self).on_except(exc_info)
