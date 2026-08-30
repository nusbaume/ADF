#Import standard modules:
from pathlib import Path
import numpy as np
import xarray as xr
import matplotlib.pyplot as plt
import matplotlib as mpl
import plotting_utils as plot_utils

#Format warning messages:
import adf_utils as utils
import warnings  # use to warn user about missing files.
warnings.formatwarning = utils.my_formatwarning

#Constants for the potential temperature -> temperature conversion:
P0 = 1.0e5              # reference pressure, Pa
KAPPA = 287.0 / 1004.0  # R_dry / cp_dry


def _zonal_mean_pressure(adf, case_name, like, season):
    """Season-averaged zonal mean pressure (Pa) on the TEM grid, or None.

    The ADF prefers the model's own pressure over pressure reconstructed from
    the hybrid coefficients: it is what the model actually used, and for the
    dry-mass vertical coordinate in recent CAM/WACCM the hybrid coefficients do
    not give pressure at all.  Which field that is depends on the grid the TEM
    output landed on -- PMID on layer midpoints, PINT on interfaces -- the same
    rule _find_pressure_field applies in regrid_and_vert_interp.py.

    'case_name' selects a test case, or None for the baseline.  'like' is the
    field being converted; the result is put on its zalat and vertical grid.
    Returns None when the pressure field is unavailable, leaving the caller to
    fall back.
    """
    lev_name = utils.vertical_dim(like)
    if lev_name is None:
        return None
    field = utils.pressure_field_name(lev_name)

    if case_name is None:
        fils = adf.data.get_ref_timeseries_file(field)
    else:
        fils = adf.data.get_timeseries_file(case_name, field)
    #End if
    if not fils:
        return None
    ds_pmid = adf.data.load_timeseries_dataset(fils)
    if ds_pmid is None or field not in ds_pmid:
        return None
    pmid = ds_pmid[field]

    #CAM writes PMID in Pa; convert here, before the arithmetic below drops attrs.
    if str(pmid.attrs.get("units", "Pa")).lower() in ("hpa", "mb", "millibars"):
        pmid = pmid * 100.0
    #End if

    #Weight by month length, matching how the TEM fields are averaged:
    month_length = pmid.time.dt.days_in_month
    if season == "ANN":
        weights = month_length / month_length.sum()
        pmid = (pmid * weights).sum(dim="time")
    else:
        grouped = month_length.groupby("time.season")
        weights = grouped / grouped.sum()
        pmid = ((pmid * weights).groupby("time.season").sum(dim="time")
                .sel(season=season))
    #End if

    #Zonal mean, then onto the TEM latitude/level grid. The TEM output has its
    #own vertical grid, so the pressure generally has to be interpolated in both
    #lat and level, not just lat.
    if "lon" in pmid.dims:
        pmid = pmid.mean(dim="lon")
    #Interpolating onto a target named 'zalat' renames the dimension for us:
    target_lat = xr.DataArray(like["zalat"].values, dims="zalat",
                              coords={"zalat": like["zalat"].values})
    pmid = pmid.interp(lat=target_lat, method="linear",
                       kwargs={"fill_value": "extrapolate"})
    #Interpolate unless the two vertical coordinates are already identical.
    #Matching sizes are not enough: the TEM grid and the model grid can have the
    #same number of levels at different pressures, and xarray would then align
    #them to an empty intersection instead of raising.
    pres_lev = utils.vertical_dim(pmid)
    if pres_lev is not None and not np.array_equal(pmid[pres_lev].values,
                                                   like[lev_name].values):
        target_lev = xr.DataArray(like[lev_name].values, dims=lev_name,
                                  coords={lev_name: like[lev_name].values})
        pmid = pmid.interp({pres_lev: target_lev}, method="linear",
                           kwargs={"fill_value": "extrapolate"})
    #End if

    return pmid


def _to_temperature(adf, case_name, theta, season):
    """Potential temperature -> temperature, using PMID when it is available."""
    pres = _zonal_mean_pressure(adf, case_name, theta, season)
    lev_name = utils.vertical_dim(theta)
    if pres is None:
        #The hybrid coordinate is only the true pressure for a hybrid-sigma
        #vertical coordinate; on the dry-mass coordinate used by recent
        #CAM/WACCM it is not, so say so rather than quietly producing a
        #slightly wrong temperature.
        field = utils.pressure_field_name(lev_name)
        label = case_name if case_name else "the baseline"
        warnings.warn(f"\t    WARNING: no {field} found for {label}, converting "
                      f"THZM with the hybrid '{lev_name}' coordinate instead. Add "
                      f"'{field}' to 'diag_var_list' for the exact conversion.")
        pres = theta[lev_name] * 100.0
    #End if
    temperature = theta * (pres / P0) ** KAPPA
    temperature.attrs['units'] = "K"
    return temperature


def tem(adf):
    """
    Plot the contents of the TEM dignostic ouput of 2-D latitude vs vertical pressure maps.
    
    Steps:
     - loop through TEM variables
     - calculate all-time fields (from individual months)
     - take difference, calculate statistics
     - make plots

    Notes:
     - If any of the TEM cases are missing, the ADF skips this plotting script and moves on.

    """

    #Notify user that script has started:
    msg = "\n  Generating TEM plots..."
    print(f"{msg}\n  {'-' * (len(msg)-3)}")

    #Special ADF variable which contains the output paths for
    #all generated plots and tables for each case:
    plot_locations = [Path(loc) for loc in adf.plot_location]

    #Check if plot output directories exist, and if not, then create them:
    for plot_loc in plot_locations:
        if not plot_loc.is_dir():
            print(f"    {plot_loc} not found, making new directory")
            plot_loc.mkdir(parents=True)

    #CAM simulation variables (this is always assumed to be a list):
    case_names = adf.get_cam_info("cam_case_name", required=True)

    res = adf.variable_defaults # will be dict of variable-specific plot preferences

    #Check if comparing against observations
    if adf.compare_obs:
        obs = True
        base_name = "Obs"
    else:
        obs = False
        base_name = adf.get_baseline_info("cam_case_name", required=True)
    #End if

    #Extract test case years
    syear_cases = adf.climo_yrs["syears"]
    eyear_cases = adf.climo_yrs["eyears"]

    #Extract baseline years (which may be empty strings if using Obs):
    syear_baseline = adf.climo_yrs["syear_baseline"]
    eyear_baseline = adf.climo_yrs["eyear_baseline"]

    #Grab all case nickname(s)
    test_nicknames = adf.case_nicknames["test_nicknames"]
    base_nickname = adf.case_nicknames["base_nickname"]
 
    #Set plot file type:
    # -- this should be set in basic_info_dict, but is not required
    # -- So check for it, and default to png
    basic_info_dict = adf.read_config_var("diag_basic_info")
    plot_type = basic_info_dict.get('plot_type', 'png')
    print(f"\t NOTE: Plot type is set to {plot_type}")

    # check if existing plots need to be redone
    redo_plot = adf.get_basic_info('redo_plot')
    print(f"\t NOTE: redo_plot is set to {redo_plot}")
    #-----------------------------------------
    
    #Initialize list of input TEM file locations
    tem_locs = []

    #Extract TEM file save locations
    tem_case_locs = adf.get_cam_info("cam_tem_loc",required=True)
    tem_base_loc = adf.get_baseline_info("cam_tem_loc")

    #If path not specified, skip TEM calculation?
    if tem_case_locs is None:
        print("\t 'cam_tem_loc' not found for test case(s) in config file, so no TEM plots will be generated.")
        return
    else:
        for tem_case_loc in tem_case_locs:
            tem_case_loc = Path(tem_case_loc)
            #Check if TEM directory exists, and if not, then create it:
            if not tem_case_loc.is_dir():
                print(f"    {tem_case_loc} not found, making new directory")
                tem_case_loc.mkdir(parents=True)
            #End if
            tem_locs.append(tem_case_loc)
        #End for

    #Set seasonal ranges:
    seasons = {"ANN": np.arange(1,13,1),
               "DJF": [12, 1, 2],
               "JJA": [6, 7, 8],
               "MAM": [3, 4, 5],
               "SON": [9, 10, 11]
               }

    #Suggestion from Rolando, if QBO is being produced, add utendvtem and utendwtem?
    if "qbo" in adf.plotting_scripts:
        var_list = ["UZM","THZM","EPFY","EPFZ","VTEM","WTEM",
                    "PSITEM","UTENDEPFD","UTENDVTEM","UTENDWTEM"]
    else:
        var_list = ["UZM","THZM","EPFY","EPFZ","VTEM","WTEM","PSITEM","UTENDEPFD"]

    #Check if comparing against obs
    if adf.compare_obs:
        obs = True
        #Set TEM file for observations
        base_file_name = 'Obs.TEMdiag.nc'
        input_loc_idx = Path(tem_locs[0])
    else:
        #Set TEM file for baseline
        base_file_name = f'{base_name}.TEMdiag_{syear_baseline}-{eyear_baseline}.nc'
        #Baseline TEM location ('cam_tem_loc' is unset when comparing to obs)
        input_loc_idx = Path(tem_base_loc)
    
    #Set full path for baseline/obs file
    tem_base = input_loc_idx / base_file_name

    #Check to see if baseline/obs TEM file exists
    if tem_base.is_file():
        ds_base = xr.open_dataset(tem_base, decode_times=False)
    else:
        print(f"\t'{base_file_name}' does not exist. TEM plots will be skipped.")
        return

    """if 'time_bnds' in ds_base:
        t = ds_base['time_bnds'].mean(dim='nbnd')
        t.attrs = ds_base['time'].attrs
        ds_base = ds_base.assign_coords({'time':t})
    elif 'time_bounds' in ds_base:
        t = ds_base['time_bounds'].mean(dim='nbnd')
        t.attrs = ds_base['time'].attrs
        ds_base = ds_base.assign_coords({'time':t})
    else:
        warnings.warn("\t    INFO: Timeseries file does not have time bounds info.")"""
    ds_base = xr.decode_cf(ds_base)

    #Open each test case's TEM file once, up front, so a missing file is reported
    #before any plotting work is done:
    case_datasets = []
    for idx,case_name in enumerate(case_names):
        tem_case = Path(tem_case_locs[idx]) / \
                   f'{case_name}.TEMdiag_{syear_cases[idx]}-{eyear_cases[idx]}.nc'
        if not tem_case.is_file():
            print(f"\t'{tem_case}' does not exist. TEM plots will be skipped.")
            return
        ds = xr.open_dataset(tem_case, decode_times=False)
        if 'time_bnds' in ds:
            t = ds['time_bnds'].mean(dim='nbnd')
            t.attrs = ds['time'].attrs
            ds = ds.assign_coords({'time':t})
        elif 'time_bounds' in ds:
            t = ds['time_bounds'].mean(dim='nbnd')
            t.attrs = ds['time'].attrs
            ds = ds.assign_coords({'time':t})
        else:
            warnings.warn("\t    INFO: TEM file does not have time bounds info.")
        case_datasets.append(xr.decode_cf(ds))
    #End for

    #Loop over variables:
    for var in var_list:
        #Notify user of variable being plotted:
        print(f"\t - TEM plots for {var}")

        if var not in ds_base:
            warnings.warn(f"\t    INFO: '{var}' not in {base_name} TEM file, skipping.")
            continue
        #End if

        #Loop over model cases:
        for idx,case_name in enumerate(case_names):

            ds = case_datasets[idx]
            plot_location = plot_locations[idx]

            if var not in ds:
                warnings.warn(f"\t    INFO: '{var}' not in {case_name} TEM file, skipping.")
                continue
            #End if

            #Extract start and end year values:
            start_year = syear_cases[idx]
            end_year   = eyear_cases[idx]

            #Loop over season dictionary:
            for s in seasons:

                #Location to save plots
                plot_name = plot_location / f"{var}_{s}_WACCM_SeasonalCycle_Mean.png"

                # Check redo_plot. If set to True: remove old plot, if it already exists:
                if (not redo_plot) and plot_name.is_file():
                    #Add already-existing plot to website (if enabled):
                    adf.debug_log(f"'{plot_name}' exists and clobber is false.")
                    adf.add_website_data(plot_name, var, case_name, season=s, plot_type="WACCM",
                                         ext="SeasonalCycle_Mean", category="TEM")
                    continue
                elif redo_plot and plot_name.is_file():
                    plot_name.unlink()
                #End if

                #Grab variable defaults for this variable
                vres = res[var]

                #Gather data for both cases
                mdata = ds[var].squeeze()
                odata = ds_base[var].squeeze()

                # APPLY UNITS TRANSFORMATION IF SPECIFIED:
                # NOTE: looks like our climo files don't have all their metadata
                mdata = mdata * vres.get("scale_factor",1) + vres.get("add_offset", 0)
                # update units
                mdata.attrs['units'] = vres.get("new_unit", mdata.attrs.get('units', 'none'))

                # Do the same for the baseline case if need be:
                if not obs:
                    odata = odata * vres.get("scale_factor",1) + vres.get("add_offset", 0)
                    # update units
                    odata.attrs['units'] = vres.get("new_unit", odata.attrs.get('units', 'none'))
                # Or for observations
                else:
                    odata = odata * vres.get("obs_scale_factor",1) + vres.get("obs_add_offset", 0)
                    # Note: we are going to assume that the specification ensures the conversion makes the units the same. Doesn't make sense to add a different unit.

                #Create array to avoid weighting missing values:
                md_ones = xr.where(mdata.isnull(), 0.0, 1.0)
                od_ones = xr.where(odata.isnull(), 0.0, 1.0)

                month_length = mdata.time.dt.days_in_month
                weights = (month_length.groupby("time.season") / month_length.groupby("time.season").sum())

                #Calculate monthly-weighted seasonal averages:
                if s == 'ANN':

                    #Calculate annual weights (i.e. don't group by season):
                    weights_ann = month_length / month_length.sum()

                    mseasons = (mdata * weights_ann).sum(dim='time')
                    mseasons = mseasons / (md_ones*weights_ann).sum(dim='time')

                    #Calculate monthly weights based on number of days:
                    if obs:
                        month_length_obs = odata.time.dt.days_in_month
                        weights_ann_obs = month_length_obs / month_length_obs.sum()
                        oseasons = (odata * weights_ann_obs).sum(dim='time')
                        oseasons = oseasons / (od_ones*weights_ann_obs).sum(dim='time')
                    else:
                        month_length_base = odata.time.dt.days_in_month
                        weights_ann_base = month_length_base / month_length_base.sum()
                        oseasons = (odata * weights_ann_base).sum(dim='time')
                        oseasons = oseasons / (od_ones*weights_ann_base).sum(dim='time')

                else:
                    #this is inefficient because we do same calc over and over
                    mseasons = (mdata * weights).groupby("time.season").sum(dim="time").sel(season=s)
                    wgt_denom = (md_ones*weights).groupby("time.season").sum(dim="time").sel(season=s)
                    mseasons = mseasons / wgt_denom

                    if obs:
                        month_length_obs = odata.time.dt.days_in_month
                        weights_obs = (month_length_obs.groupby("time.season") / month_length_obs.groupby("time.season").sum())
                        oseasons = (odata * weights_obs).groupby("time.season").sum(dim="time").sel(season=s)
                        wgt_denom = (od_ones*weights_obs).groupby("time.season").sum(dim="time").sel(season=s)
                        oseasons = oseasons / wgt_denom
                    else:
                        month_length_base = odata.time.dt.days_in_month
                        weights_base = (month_length_base.groupby("time.season") / month_length_base.groupby("time.season").sum())
                        oseasons = (odata * weights_base).groupby("time.season").sum(dim="time").sel(season=s)
                        wgt_denom_base = (od_ones*weights_base).groupby("time.season").sum(dim="time").sel(season=s)
                        oseasons = oseasons / wgt_denom_base

                # Derive zonal mean temperature from potential temperature.
                if var == "THZM":
                    #Each side is converted with its own pressure; the test case
                    #and the baseline need not share a vertical coordinate.
                    mseasons = _to_temperature(adf, case_name, mseasons, s)
                    if not obs:
                        oseasons = _to_temperature(adf, None, oseasons, s)
                    #End if
                #End if

                if var == "UTENDEPFD":
                    mseasons = mseasons*1000
                    oseasons = oseasons*1000
                #difference: each entry should be (lev, zalat). Test and
                #baseline can be on different vertical grids -- observations
                #always are, and CAM may write the zonal-mean stream on
                #midpoints for one case and interfaces for another -- in which
                #case there is nothing to difference.
                #Comparable means the two sit on the same kind of grid AND
                #share enough levels to contour: xarray aligns them on their
                #common levels, and equal level counts do not imply equal
                #levels (ERA5 has 37 pressure levels against WACCM's 71).
                lev_m = utils.vertical_dim(mseasons)
                lev_b = utils.vertical_dim(oseasons)
                comparable = lev_m == lev_b
                dseasons = mseasons-oseasons if comparable else None
                if dseasons is None or dseasons[lev_m].size < 2:
                    comparable = False
                    dseasons = xr.zeros_like(mseasons)
                #End if

                #percent change, following the convention in plotting_functions
                pseasons = (dseasons / np.abs(oseasons) * 100.0 if comparable
                            else dseasons)
                pseasons = pseasons.where(np.isfinite(pseasons), np.nan).fillna(0.0)

                #Gather contour plot options
                cp_info = plot_utils.prep_contour_plot(mseasons, oseasons, dseasons,
                                                       pseasons, **vres)
                clevs = np.unique(np.array(cp_info['levels1']))
                norm = cp_info['norm1']
                cmap = cp_info['cmap1']
                clevs_diff = np.unique(np.array(cp_info['levelsdiff']))

                # mesh for plots -- each panel gets its own, because the baseline
                # (especially observations) can be on a different vertical grid
                # than the test case, and the difference is on their intersection.
                def _mesh(da):
                    return np.meshgrid(da['zalat'], da[utils.vertical_dim(da)])
                lats, levs = _mesh(mseasons)
                lats_b, levs_b = _mesh(oseasons)

                # Find the next value below highest vertical level
                prev_major_tick = 10 ** (np.floor(np.log10(np.min(levs))))

                # Set padding for colorbar form axis
                cmap_pad = 0.005

                # create figure object
                fig = plt.figure(figsize=(14,10))
                # LAYOUT WITH GRIDSPEC
                # 4 rows, 8 columns, but each map will take up 4 columns and 2 rows
                gs = mpl.gridspec.GridSpec(4, 8, wspace=0.75,hspace=0.5)
                ax1 = plt.subplot(gs[0:2, :4], **cp_info['subplots_opt'])
                ax2 = plt.subplot(gs[0:2, 4:], **cp_info['subplots_opt'])
                ax3 = plt.subplot(gs[2:, 2:6], **cp_info['subplots_opt'])
                ax = [ax1,ax2,ax3]

                #Contour fill
                img0 = ax[0].contourf(lats, levs,mseasons, levels=clevs, norm=norm, cmap=cmap)
                img1 = ax[1].contourf(lats_b, levs_b,oseasons, levels=clevs, norm=norm, cmap=cmap)
                    
                #Add contours for highlighting
                c0 = ax[0].contour(lats,levs,mseasons,levels=clevs[::2], norm=norm,
                                    colors="k", linewidths=0.5)

                #Check if contour labels need to be adjusted
                #ie if the values are large and/or in scientific notation, just label the 
                #contours with the leading numbers.
                #EXAMPLE: plot values are 200000; plot the contours as 2.0 and let the colorbar
                #         indicate that it is e5.
                fmt = {}
                if 'contour_adjust' in vres:
                    test_strs = c0.levels/float(vres['contour_adjust'])
                    for l, str0 in zip(c0.levels, test_strs):
                        fmt[l] = str0

                    # Add contour labels
                    plt.clabel(c0, inline=True, fontsize=8, levels=c0.levels, fmt=fmt)
                else:
                    # Add contour labels
                    plt.clabel(c0, inline=True, fontsize=8, levels=c0.levels)

                #Add contours for highlighting
                c1 = ax[1].contour(lats_b,levs_b,oseasons,levels=clevs[::2], norm=norm,
                                    colors="k", linewidths=0.5)

                #Check if contour labels need to be adjusted
                #ie if the values are large and/or in scientific notation, just label the 
                #contours with the leading numbers.
                #EXAMPLE: plot values are 200000; plot the contours as 2.0 and let the colorbar
                #         indicate that it is e5.
                fmt = {}
                if 'contour_adjust' in vres:
                    base_strs = c1.levels/float(vres['contour_adjust'])
                    for l, str0 in zip(c1.levels, base_strs):
                        fmt[l] = str0

                    # Add contour labels
                    plt.clabel(c1, inline=True, fontsize=8, levels=c1.levels, fmt=fmt)
                else:
                    # Add contour labels
                    plt.clabel(c1, inline=True, fontsize=8, levels=c1.levels)


                #Nothing to draw when the two cases could not be differenced:
                if not comparable:
                    #Set empty message for comparison of cases with different vertical levels
                    #TODO: Work towards getting the vertical and horizontal interpolations!! - JR
                    empty_message = "These have different vertical levels\nCan't compare cases currently"
                    props = {'boxstyle': 'round', 'facecolor': 'wheat', 'alpha': 0.9}
                    prop_x = 0.18
                    prop_y = 0.42
                    ax[2].text(prop_x, prop_y, empty_message,
                                    transform=ax[2].transAxes, bbox=props)
                else:
                    lats_d, levs_d = _mesh(dseasons)
                    img2 = ax[2].contourf(lats_d, levs_d, dseasons,
                                            #cmap="BrBG",
                                            cmap=cp_info['cmapdiff'],
                                            levels=clevs_diff,
                                            norm=cp_info['normdiff'])
                    ax[2].contour(lats_d, levs_d, dseasons, colors="k", linewidths=0.5,
                                    levels=clevs_diff[::2], norm=cp_info['normdiff'])
                    cp_info['diff_colorbar_opt']["label"] = cp_info['colorbar_opt']["label"]
                    plt.colorbar(img2, ax=ax[2], location='right', pad=cmap_pad,**cp_info['diff_colorbar_opt'])

                #Format y-axis
                for i,a in enumerate(ax[:]):
                    a.set_yscale("log")
                    a.set_xlabel("Latitude")
                    # Only plot y-axis label for test case
                    if i == 0:
                        a.set_ylabel('Pressure [hPa]', va='center', rotation='vertical')
                    if 'ylim' in vres:
                        y_lims = [float(lim) for lim in vres['ylim']]
                        y_lims[-1]=prev_major_tick
                        a.set_ylim(y_lims)
                    else:
                        a.set_ylim(a.get_ylim()[::-1])

                # Format color bars
                plt.colorbar(img1, ax=ax[1], location='right', pad=cmap_pad,**cp_info['colorbar_opt'])
                # Remove the colorbar label for baseline
                cp_info['colorbar_opt'].pop("label", None)
                plt.colorbar(img0, ax=ax[0], location='right', pad=cmap_pad,**cp_info['colorbar_opt'])

                #Variable plot title name
                longname = vres["long_name"]
                plt.suptitle(f'{longname}: {s}', fontsize=20, y=.97)

                test_yrs = f"{start_year}-{end_year}"
                
                plot_title = r"$\mathbf{Test}:$"+f"{test_nicknames[idx]}\nyears: {test_yrs}"
                ax[0].set_title(plot_title, loc='left', fontsize=10)

                if obs:
                    obs_title = Path(vres["obs_name"]).stem
                    ax[1].set_title(f"{obs_title}\n",fontsize=10)

                else:
                    base_yrs = f"{syear_baseline}-{eyear_baseline}"
                    plot_title = r"$\mathbf{Baseline}:$"+f"{base_nickname}\nyears: {base_yrs}"
                    ax[1].set_title(plot_title, loc='left', fontsize=10)
                
                #Set main title for difference plots column
                ax[2].set_title(r"$\mathbf{Test} - \mathbf{Baseline}$",fontsize=10)

                #Write the figure to provided workspace/file:
                fig.savefig(plot_name, bbox_inches='tight', dpi=300)

                #Add plot to website (if enabled):
                adf.add_website_data(plot_name, var, case_name, season=s, plot_type="WACCM",
                                     ext="SeasonalCycle_Mean",category="TEM")

                plt.close()
    print("  ...TEM plots have been generated successfully.")

# Helper functions
##################