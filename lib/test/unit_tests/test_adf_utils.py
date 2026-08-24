"""
Collection of python unit tests
for the "adf_utils" helper functions.
"""

#+++++++++++++++++++++++
#Import required modules
#+++++++++++++++++++++++

import unittest
import sys
import os
import os.path
import tempfile

#Set relevant path variables:
_CURRDIR = os.path.abspath(os.path.dirname(__file__))
_ADF_LIB_DIR = os.path.join(_CURRDIR, os.pardir, os.pardir)

#Add ADF "lib" directory to python path:
sys.path.append(_ADF_LIB_DIR)

#adf_utils pulls in the scientific stack (xarray, geocat, ...), which isn't
#always present in a bare test environment, so skip rather than error there:
try:
    from adf_utils import find_ts_files
    _HAS_ADF_UTILS = True
except ImportError:
    _HAS_ADF_UTILS = False

#++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
#Main adf_utils testing routine, used when script is run directly
#++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

@unittest.skipUnless(_HAS_ADF_UTILS, "adf_utils dependencies not available")
class AdfUtilsTestRoutine(unittest.TestCase):

    """
    Unit tests for the time series file search helper, which has to cope with
    both ADF's flat time series directory and GenTS's nested
    <component>/proc/tseries/<frequency>/ layout.
    """

    def test_find_ts_files_flat(self):

        """
        Check that a file sitting directly in the search directory is found.
        """

        with tempfile.TemporaryDirectory() as tmpdir:
            fname = "case.cam.h0a.T.000101-001112.nc"
            open(os.path.join(tmpdir, fname), "w").close()

            found = find_ts_files(tmpdir, "case.cam.h0a.T.*nc")

            self.assertEqual([f.name for f in found], [fname])

    def test_find_ts_files_nested(self):

        """
        Check that a file buried in a GenTS-style sub-directory is found when
        nothing matches at the top level.
        """

        with tempfile.TemporaryDirectory() as tmpdir:
            subdir = os.path.join(tmpdir, "atm", "proc", "tseries", "month_1")
            os.makedirs(subdir)
            fname = "case.cam.h0a.T.000101-001112.nc"
            open(os.path.join(subdir, fname), "w").close()

            found = find_ts_files(tmpdir, "case.cam.h0a.T.*nc")

            self.assertEqual([f.name for f in found], [fname])

    def test_find_ts_files_prefers_flat(self):

        """
        Check that the flat match wins, so that a nested directory of files
        from some other run can't shadow the expected location.
        """

        with tempfile.TemporaryDirectory() as tmpdir:
            subdir = os.path.join(tmpdir, "atm", "proc", "tseries", "month_1")
            os.makedirs(subdir)
            fname = "case.cam.h0a.T.000101-001112.nc"
            open(os.path.join(tmpdir, fname), "w").close()
            open(os.path.join(subdir, fname), "w").close()

            found = find_ts_files(tmpdir, "case.cam.h0a.T.*nc")

            self.assertEqual(len(found), 1)
            self.assertEqual(os.path.dirname(str(found[0])), tmpdir)

    def test_find_ts_files_no_match(self):

        """
        Check that a search with no matches returns an empty list, rather
        than raising, so callers can warn and move on.
        """

        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "case.cam.h0a.T.000101-001112.nc"), "w").close()

            self.assertEqual(find_ts_files(tmpdir, "case.cam.h0a.PRECT.*nc"), [])

#++++++++++++++++++

#Run unit tests if this script is called directly:
if __name__ == "__main__":
    unittest.main()

#############
#End of file
