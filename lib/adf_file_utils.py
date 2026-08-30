"""
Time series file discovery helpers.

Kept apart from adf_utils so they can be unit tested without the scientific
stack: the ADF unit test workflow installs only PyYAML and pytest, so anything
that imports xarray/geocat at module level cannot be exercised in CI.  This
module imports nothing but pathlib.

Functions
---------
find_ts_files(ts_loc, pattern, recursive=True)
    Locate time series files matching a glob pattern under a directory.
ts_files_overlap(fils)
    Report whether a set of time series files cover overlapping periods.
ts_file_span(fils)
    Report the period a set of time series files covers, taken together.

Notes
-----
Re-exported by adf_utils, so ``utils.find_ts_files(...)`` keeps working for
every existing caller.
"""

from pathlib import Path


def find_ts_files(ts_loc, pattern, recursive=True):
    """
    Locate time series files matching ``pattern`` underneath ``ts_loc``.

    Searches ``ts_loc`` itself first, which is where ADF's own time series step
    and a flat GenTS run both put their files.  Only if that finds nothing does
    it fall back to a recursive search, so that a GenTS archive laid out as
    <component>/proc/tseries/<frequency>/ can be used by pointing ``cam_ts_loc``
    at the top of the tree instead of the frequency sub-directory.

    Parameters
    ----------
    ts_loc : str or Path
        directory to search
    pattern : str
        glob pattern, e.g. "case.cam.h0a.T.*nc"
    recursive : bool, optional
        Whether to fall back to a recursive search when the flat one finds
        nothing.  Default is ``True``.  A missing variable is a normal
        condition, so a caller trying many patterns in a row should pass
        ``False`` and make a single recursive attempt at the end rather than
        walking the whole tree once per pattern.

    Returns
    -------
    list of Path
        Matching files, sorted; empty if nothing matches.
    """
    ts_loc = Path(ts_loc)
    found = sorted(ts_loc.glob(pattern))
    if found or not recursive:
        return found
    #End if
    return sorted(ts_loc.rglob(pattern))


def _ts_file_spans(fils):
    """
    Parse the {start}-{end} date token out of each time series file name.

    Parameters
    ----------
    fils : list
        strings or paths to time series files

    Returns
    -------
    list of tuple or None
        (start, end) string pairs sorted chronologically, or ``None`` if any
        name could not be parsed or the dates do not all use the same width.
        Callers treat ``None`` as "make no promises about these files".
    """
    spans = []
    for fil in fils:
        #Last dot-separated token of the stem -- second-to-last of the file
        #name -- e.g. "001001-001112" in "case.cam.h0a.T.001001-001112.nc":
        date_str = Path(fil).stem.split(".")[-1]
        start, sep, end = date_str.partition("-")
        if not sep or not start.isdigit() or not end.isdigit():
            #Unrecognized name, so make no promises about it:
            return None
        spans.append((start, end))
    #End for

    #Zero-padded dates of equal width sort chronologically as strings, but
    #mixed widths (e.g. YYYY next to YYYYMM) would not, so bail out on those:
    if len({len(s) for span in spans for s in span}) != 1:
        return None
    #End if

    return sorted(spans)


def ts_files_overlap(fils):
    """
    Report whether time series files cover overlapping periods.

    ADF and GenTS both name time series files
    ``{case}.{stream}.{variable}.{start}-{end}.nc``, where the dates are
    zero-padded and all use the same width for a given variable.  A variable
    split into consecutive chunks (e.g. 001001-001912 then 002001-002912) can
    safely be opened together; two overlapping sets (e.g. years 1-20 alongside
    years 1-40, which happens when a run is extended and the time series are
    remade over a longer period) cannot, because the combined time axis would
    contain duplicates.

    Parameters
    ----------
    fils : list
        strings or paths to time series files

    Returns
    -------
    bool
        True if the files overlap, or if the dates could not be read from the
        names -- in both cases the caller should not blindly combine them.
        False if the files are non-overlapping and safe to open together.
    """
    if len(fils) < 2:
        return False
    #End if

    spans = _ts_file_spans(fils)
    if spans is None:
        return True
    #End if

    for (_, prev_end), (next_start, _) in zip(spans, spans[1:]):
        if next_start <= prev_end:
            return True
    #End for

    return False


def ts_file_span(fils):
    """
    Report the period covered by a set of time series files, taken together.

    Used to name a file derived from several chunked constituent files: the
    derived file has to advertise the whole span it actually contains, not the
    span of whichever chunk happened to sort first.  For a single file this is
    just that file's own dates, so names are unchanged for the common case.

    Parameters
    ----------
    fils : list
        strings or paths to time series files

    Returns
    -------
    tuple of str or None
        (start, end) as they appear in the file names, or ``None`` if the
        dates could not be read.
    """
    spans = _ts_file_spans(fils)
    if not spans:
        return None
    #End if

    #Sorted by start, so the earliest start leads; take the latest end
    #explicitly rather than assuming the last entry carries it:
    return spans[0][0], max(end for _, end in spans)
