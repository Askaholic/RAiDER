#!/usr/bin/env python3
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#
# Author: Jeremy Maurer, Raymond Hogenson & David Bekaert
# Copyright 2019, by the California Institute of Technology. ALL RIGHTS
# RESERVED. United States Government Sponsorship acknowledged.
#
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
import logging
import os

import numpy as np

from RAiDER.demdownload import download_dem
from RAiDER.utilFcns import gdal_open

log = logging.getLogger(__name__)


def readLL(*args):
    '''
    Parse lat/lon/height inputs and return
    the appropriate outputs
    '''
    if len(args) == 2:
        flag = 'files'
    elif len(args) == 4:
        flag = 'bounding_box'
    elif len(args) == 1:
        flag = 'station_list'
    else:
        raise RuntimeError('llreader: Cannot parse args')

    # Lats/Lons
    if flag == 'files':
        # If they are files, open them
        lat, lon = args
        lats, latproj, _ = gdal_open(lat, returnProj=True)
        lons, lonproj, _ = gdal_open(lon, returnProj=True)
    elif flag == 'bounding_box':
        S, N, W, E = args
        lats = np.array([float(N), float(S)])
        lons = np.array([float(E), float(W)])
        latproj = lonproj = 'EPSG:4326'
        if (lats[0] == lats[1]) | (lons[0] == lons[1]):
            raise RuntimeError('You have passed a zero-size bounding box: {}'
                               .format(args.bounding_box))
    elif flag == 'station_list':
        lats, lons = readLLFromStationFile(*args)
        latproj = lonproj = 'EPSG:4326'
    else:
        # They'll get set later with weather
        lats = lons = None
        latproj = lonproj = None
        #raise RuntimeError('readLL: unknown flag')

    [lats, lons] = enforceNumpyArray(lats, lons)
    bounds = (np.nanmin(lats), np.nanmax(lats), np.nanmin(lons), np.nanmax(lons))

    return lats, lons, latproj, lonproj, bounds


def getHeights(lats, lons, heights, useWeatherNodes=False):
    '''
    Fcn to return heights from a DEM, either one that already exists
    or will download one if needed.
    '''
    height_type, height_data = heights
    in_shape = lats.shape

    if height_type == 'dem':
        try:
            hts = gdal_open(height_data)
        except:
            log.warning(
                'File %s could not be opened; requires GDAL-readable file.',
                height_data, exc_info=True
            )
            log.info('Proceeding with DEM download')
            height_type = 'download'

    elif height_type == 'lvs':
        if height_data is not None and useWeatherNodes:
            hts = height_data
        elif height_data is not None:
            hts = height_data
            latlist, lonlist, hgtlist = [], [], []
            for ht in hts:
                latlist.append(lats.flatten())
                lonlist.append(lons.flatten())
                hgtlist.append(np.array([ht] * len(lats.flatten())))
            lats = np.array(latlist).reshape(in_shape + (len(height_data),))
            lons = np.array(lonlist).reshape(in_shape + (len(height_data),))
            hts = np.array(hgtlist).reshape(in_shape + (len(height_data),))
        else:
            raise RuntimeError('Heights must be specified with height option "lvs"')

    elif height_type == 'merge':
        import pandas as pd
        for f in height_data:
            data = pd.read_csv(f)
            lats = data['Lat'].values
            lons = data['Lon'].values
            hts = download_dem(lats, lons, outName=f, save_flag='merge')
    else:
        if useWeatherNodes:
            hts = None
            height_type = 'skip'
        else:
            height_type = 'download'

    if height_type == 'download':
        hts = download_dem(lats, lons, outName=os.path.abspath(height_data))

    [lats, lons, hts] = enforceNumpyArray(lats, lons, hts)

    return lats, lons, hts


def enforceNumpyArray(*args):
    '''
    Enforce that a set of arguments are all numpy arrays.
    Raise an error on failure.
    '''
    return [checkArg(a) for a in args]


def checkArg(arg):

    if arg is None:
        return None
    else:
        import numpy as np
        try:
            return np.array(arg)
        except:
            raise RuntimeError('checkArg: Cannot covert argument to numpy arrays')


def readLLFromStationFile(fname):
    '''
    Helper fcn for checking argument compatibility
    '''
    try:
        import pandas as pd
        stats = pd.read_csv(fname)
        return stats['Lat'].values, stats['Lon'].values
    except:
        lats, lons = [], []
        with open(fname, 'r') as f:
            for i, line in enumerate(f):
                if i == 0:
                    continue
                lat, lon = [float(f) for f in line.split(',')[1:3]]
                lats.append(lat)
                lons.append(lon)
        return lats, lons
