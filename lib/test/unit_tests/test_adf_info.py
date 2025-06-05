"""
Collection of python unit tests
for the "AdfInfo" class.
"""

#+++++++++++++++++++++++
#Import required modules
#+++++++++++++++++++++++

import unittest
import sys
import os
import os.path

#Set relevant path variables:
_CURRDIR = os.path.abspath(os.path.dirname(__file__))
_ADF_LIB_DIR = os.path.join(_CURRDIR, os.pardir, os.pardir)
_TEST_FILES_DIR = os.path.join(_CURRDIR, "test_files")

#Add ADF "lib" directory to python path:
sys.path.append(_ADF_LIB_DIR)

#Import AdfInfo class and AdfError
from adf_info import AdfInfo
from adf_base import AdfError

#++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
#Main AdfInfo testing routine, used when script is run directly
#++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

class AdfInfoTestRoutine(unittest.TestCase):

    """
    Runs all of the unit tests
    for the AdfInfo class.  Ideally
    this set of tests will provide
    complete code coverage for AdfInfo.
    """
    def test_AdfInfo_create(self):

        """
        Check that the AdfInfo class can
        be initialized properly.
        """

        #Use example config file:
        baseline_example_file = os.path.join(_ADF_LIB_DIR, os.pardir, "config_cam_baseline_example.yaml")

        #Create AdfInfo object:
        adf_test = AdfInfo(baseline_example_file)

        #Assert that new object is of the "AdfConfig" class:
        self.assertIsInstance(adf_test, AdfConfig)

        #Also check that "read_config_var" works as expected:
        #basic_diag_dict = adf_test.read_config_var("diag_basic_info")

        #check_user = adf_test.read_config_var("user")
        #check_user_expected = 'USER-NAME-NOT-SET'
        #self.assertEqual(check_user, check_user_expected)

        #obs_data_loc = adf_test.read_config_var("obs_data_loc", conf_dict=basic_diag_dict)

        #self.assertEqual(obs_data_loc, "/glade/campaign/cgd/amp/amwg/ADF_obs")

    #####

#++++++++++++++++++++++++++++++++++++++++++++++++
#Run unit tests if this script is called directly
#++++++++++++++++++++++++++++++++++++++++++++++++

if __name__ == "__main__":
    unittest.main()

