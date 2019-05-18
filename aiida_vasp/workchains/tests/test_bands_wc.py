"""
Test submitting a ConvergenceWorkChain.

Only `run` currently works.

"""
# pylint: disable=unused-import,wildcard-import,unused-wildcard-import,unused-argument,redefined-outer-name, too-many-statements
from __future__ import print_function

import numpy as np
import pytest
from aiida.common.extendeddicts import AttributeDict

from aiida_vasp.utils.fixtures import *
from aiida_vasp.utils.fixtures.data import POTCAR_FAMILY_NAME, POTCAR_MAP
from aiida_vasp.utils.fixtures.testdata import data_path
from aiida_vasp.utils.aiida_utils import get_data_node, get_current_user, aiida_version, cmp_version
from aiida_vasp.parsers.file_parsers.poscar import PoscarParser
from aiida_vasp.parsers.file_parsers.incar import IncarParser
from aiida_vasp.utils.aiida_utils import create_authinfo


@pytest.mark.wc
@pytest.mark.skipif(aiida_version() < cmp_version('1.0.0a1'), reason='work.Runner not available before 1.0.0a1')
def test_bands_wc(fresh_aiida_env, potentials, mock_vasp):
    """Test with mocked vasp code."""
    from aiida.orm import Code
    from aiida.plugins import WorkflowFactory, DataFactory
    #from aiida import work
    from aiida.engine import run
    rmq_config = None
    inputs = AttributeDict()
    inputs.poll_interval = 0
    inputs.rmq_config= rmq_config
    inputs.enable_persistence = True
    #runner = runners.Runner(poll_interval=0., rmq_config=rmq_config, enable_persistence=True)
    #runner = runners.Runner(**inputs)
    #runners.set_runner(runner)

    workchain = WorkflowFactory('vasp.bands')

    mock_vasp.store()
    create_authinfo(computer=mock_vasp.computer, store=True)

    structure = PoscarParser(file_path=data_path('test_bands_wc', 'inp', 'POSCAR')).structure
    parameters = IncarParser(file_path=data_path('test_bands_wc', 'inp', 'INCAR')).incar
    parameters['system'] = 'test-case:test_bands_wc'
    chgcar = get_data_node('vasp.chargedensity', file=data_path('test_bands_wc', 'inp', 'CHGCAR'))
    kpoints = DataFactory('array.kpoints')()
    kpoints.set_kpoints_mesh([7, 7, 7])


    restart_clean_workdir = get_data_node('bool', False)
    restart_clean_workdir.store()

    inputs = AttributeDict()
    inputs.code = Code.get_from_string('mock-vasp@localhost')
    inputs.structure = structure
    inputs.parameters = get_data_node('dict', dict=parameters)
    inputs.kpoints = kpoints
    inputs.potential_family = get_data_node('str', POTCAR_FAMILY_NAME)
    inputs.potential_mapping = get_data_node('dict', dict=POTCAR_MAP)
    inputs.options = get_data_node(
        'dict',
        dict={
            'withmpi': False,
            'queue_name': 'None',
            'resources': {
                'num_machines': 1,
                'num_mpiprocs_per_machine': 1
            },
            'max_wallclock_seconds': 3600
        })
    inputs.max_iterations = get_data_node('int', 1)
    inputs.clean_workdir = get_data_node('bool', False)
    inputs.verbose = get_data_node('bool', True)
    inputs.chgcar = chgcar
    #results = work.run(workchain, **inputs)
    results = run(workchain, **inputs)

    assert 'output_parameters_seekpath' in results
    assert 'output_bands' in results
    assert 'output_kpoints' in results
    assert 'output_structure_primitive' in results

    seekpath_parameters = results['output_parameters_seekpath'].get_dict()
    assert seekpath_parameters['bravais_lattice'] == 'cF'
    assert seekpath_parameters['path'][0] == ['GAMMA', 'X']
    assert seekpath_parameters['path'][2] == ['K', 'GAMMA']
    assert len(seekpath_parameters['explicit_kpoints_linearcoord']) == 98
    assert seekpath_parameters['explicit_kpoints_linearcoord'][0:4] == [0.0, 0.0528887652119494, 0.105777530423899, 0.158666295635848]
    kpoints = results['output_kpoints'].get_kpoints()
    np.set_printoptions(threshold=np.nan)
    np.testing.assert_allclose(kpoints[0, 0:3], np.array([0., 0., 0.]))
    #np.testing.assert_allclose(kpoints[5, 0:3], np.array([0.11363636, 0., 0.11363636]))
    np.testing.assert_allclose(kpoints[97, 0:3], np.array([0.5, 0., 0.5]))
    bands = results['output_bands'].get_bands()
    assert bands.shape == (1, 98, 20)
    np.testing.assert_allclose(bands[0, 0, 0:3], np.array([-6.0753, 6.0254, 6.0254]))
    np.testing.assert_allclose(bands[0, 2, 0:3], np.array([-6.0386, 5.7955, 5.8737]))
    np.testing.assert_allclose(bands[0, 97, 0:3], np.array([-1.867, -1.867, 3.1102]))
