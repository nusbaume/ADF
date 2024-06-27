##################
#Warnings function
##################

import warnings  # use to warn user about missing files.
def my_formatwarning(msg, *args, **kwargs):
    # ignore everything except the message
    return str(msg) + '\n'
warnings.formatwarning = my_formatwarning


import xarray as xr  # module-level import so all functions can get to it.

import multiprocessing as mp
import x4c
import os
import sys


##############
#Main function
##############

def create_x4c_climos(adf, clobber=False, search=None):
    """
    This is an example function showing
    how to set-up a time-averaging method
    for calculating climatologies from
    CAM time series files using
    multiprocessing for parallelization.

    Description of needed inputs from ADF:

    case_name    -> Name of CAM case provided by "cam_case_name"
    input_ts_loc -> Location of CAM time series files provided by "cam_ts_loc"
    output_loc   -> Location to write CAM climo files to, provided by "cam_climo_loc"
    var_list     -> List of CAM output variables provided by "diag_var_list"

    Optional keyword arguments:

        clobber -> whether to overwrite existing climatology files. Defaults to False (do not delete).

        search  -> optional; if supplied requires a string used as a template to find the time series files
                using {CASE} and {VARIABLE} and otherwise an arbitrary shell-like globbing pattern:
                example 1: provide the string "{CASE}.*.{VARIABLE}.*.nc" this is the default
                example 2: maybe CASE is not necessary because post-process destroyed the info "post_process_text-{VARIABLE}.nc"
                example 3: order does not matter "{VARIABLE}.{CASE}.*.nc"
                Only CASE and VARIABLE are allowed because they are arguments to the averaging function
    """

    #Import necessary modules:
    from pathlib import Path
    from adf_base import AdfError

    #Notify user that script has started:
    print("\n  Calculating CAM climatologies...")

    # Set up multiprocessing pool to parallelize writing climo files.
    number_of_cpu = adf.num_procs  # Get number of available processors from the ADF

    #Extract needed quantities from ADF object:
    #-----------------------------------------
    var_list = adf.diag_var_list

    #CAM simulation variables (These quantities are always lists):
    case_names    = adf.get_cam_info("cam_case_name", required=True)
    input_ts_locs = adf.get_cam_info("cam_ts_loc", required=True)
    output_locs   = adf.get_cam_info("cam_climo_loc", required=True)
    calc_climos   = adf.get_cam_info("calc_cam_climo")
    overwrite     = adf.get_cam_info("cam_overwrite_climo")

    #Extract simulation years:
    start_year = adf.climo_yrs["syears"]
    end_year   = adf.climo_yrs["eyears"]

    #If variables weren't provided in config file, then make them a list
    #containing only None-type entries:
    if not calc_climos:
        calc_climos = [None]*len(case_names)
    if not overwrite:
        overwrite = [None]*len(case_names)
    #End if

    #Check if a baseline simulation is also being used:
    if not adf.get_basic_info("compare_obs"):
        #Extract CAM baseline variaables:
        baseline_name     = adf.get_baseline_info("cam_case_name", required=True)
        input_ts_baseline = adf.get_baseline_info("cam_ts_loc", required=True)
        output_bl_loc     = adf.get_baseline_info("cam_climo_loc", required=True)
        calc_bl_climos    = adf.get_baseline_info("calc_cam_climo")
        ovr_bl            = adf.get_baseline_info("cam_overwrite_climo")

        #Extract baseline years:
        bl_syr = adf.climo_yrs["syear_baseline"]
        bl_eyr = adf.climo_yrs["eyear_baseline"]

        #Append to case lists:
        case_names.append(baseline_name)
        input_ts_locs.append(input_ts_baseline)
        output_locs.append(output_bl_loc)
        calc_climos.append(calc_bl_climos)
        overwrite.append(ovr_bl)
        start_year.append(bl_syr)
        end_year.append(bl_eyr)
    #-----------------------------------------

    # Check whether averaging interval is supplied
    # -> using only years takes from the beginning of first year to end of second year.
    # -> slice('1991','1998') will get all of [1991,1998].
    # -> slice(None,None) will use all times.


    #Loop over CAM cases:
    for case_idx, case_name in enumerate(case_names):

        #Check if climatology is being calculated.
        #If not then just continue on to the next case:
        if not calc_climos[case_idx]:
            continue

        #Notify user of model case being processed:
        print(f"\t Calculating climatologies for case '{case_name}' :")

        #Create "Path" objects:
        input_location  = Path(input_ts_locs[case_idx])
        output_location = Path(output_locs[case_idx])

        #Check that time series input directory actually exists:
        if not input_location.is_dir():
            errmsg = f"Time series directory '{input_ts_locs}' not found.  Script is exiting."
            raise AdfError(errmsg)

        #Check if climo directory exists, and if not, then create it:
        if not output_location.is_dir():
            print(f"\t    {output_location} not found, making new directory")
            output_location.mkdir(parents=True)

        #Create symbolic link with path needed by x4c:
        x4c_input_loc = Path(os.path.join(input_location, "x4c_ts", "atm", "proc", "tseries"))
        x4c_input_loc.mkdir(parents=True, exist_ok=True)

        tmp_link = os.path.join(x4c_input_loc, "_tmp_dir")
        target_link = os.path.join(x4c_input_loc, "month_1")
        os.symlink(input_location, tmp_link, target_is_directory=True)
        os.rename(tmp_link, target_link)

        #Create x4c timeseries object:
        x4c_ts_dirpath = Path(os.path.join(input_location, "x4c_ts"))
        x4c_case = x4c.Timeseries(x4c_ts_dirpath)

        #Generate climatology file:
        x4c_case.gen_climo(
             output_dirpath=output_location,
             casename=case_name,
             timespan=(start_year[case_idx], end_year[case_idx]),
             comp='atm',
             nproc=number_of_cpu,
             overwrite=overwrite[case_idx],
             regrid=False
             )

    #End of model case loop
    #----------------------

    #Notify user that script has ended:
    print("  ...CAM climatologies have been calculated successfully.")

##############
#End of script
##############

