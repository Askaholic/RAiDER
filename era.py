"""
Read model level WRF ECMWF file, maybe download it from the internet, idk.
"""


import datetime
import numpy as np
import pyproj
import tempfile
import scipy.io
import reader
import wrf

try:
    import ecmwfapi
except ImportError as e:
    ecmwfapi_error = e


era_interim_classname = 'ei'
era5_classname = 'ea'


# This function is copied (with slight modification) from
# https://confluence.ecmwf.int//display/CKB/ERA-Interim%3A+compute+geopotential+on+model+levels#ERA-Interim:computegeopotentialonmodellevels-Step2:Computegeopotentialonmodellevels.
# That script is licensed under the Apache license. I don't know if this
# is legal.
def calculategeoh(z, lnsp, ts, qs):
    heighttoreturn = np.zeros_like(ts)
    pressurelvs = np.zeros_like(ts)

    Rd = 287.06

    z_h = 0

    #surface pressure
    sp = np.exp(lnsp)

    # A and B parameters to calculate pressures for model levels,
    #  extracted from an ECMWF ERA-Interim GRIB file and then hardcoded here
    pv60 =  [
      0.0000000000e+000, 2.0000000000e+001, 3.8425338745e+001, 6.3647796631e+001, 9.5636962891e+001,
      1.3448330688e+002, 1.8058435059e+002, 2.3477905273e+002, 2.9849584961e+002, 3.7397192383e+002,
      4.6461816406e+002, 5.7565112305e+002, 7.1321801758e+002, 8.8366040039e+002, 1.0948347168e+003,
      1.3564746094e+003, 1.6806403809e+003, 2.0822739258e+003, 2.5798886719e+003, 3.1964216309e+003,
      3.9602915039e+003, 4.9067070313e+003, 6.0180195313e+003, 7.3066328125e+003, 8.7650546875e+003,
      1.0376125000e+004, 1.2077445313e+004, 1.3775324219e+004, 1.5379804688e+004, 1.6819472656e+004,
      1.8045183594e+004, 1.9027695313e+004, 1.9755109375e+004, 2.0222203125e+004, 2.0429863281e+004,
      2.0384480469e+004, 2.0097402344e+004, 1.9584328125e+004, 1.8864750000e+004, 1.7961359375e+004,
      1.6899468750e+004, 1.5706449219e+004, 1.4411125000e+004, 1.3043218750e+004, 1.1632757813e+004,
      1.0209500000e+004, 8.8023554688e+003, 7.4388046875e+003, 6.1443164063e+003, 4.9417773438e+003,
      3.8509133301e+003, 2.8876965332e+003, 2.0637797852e+003, 1.3859125977e+003, 8.5536181641e+002,
      4.6733349609e+002, 2.1039389038e+002, 6.5889236450e+001, 7.3677425385e+000, 0.0000000000e+000,
      0.0000000000e+000, 0.0000000000e+000, 0.0000000000e+000, 0.0000000000e+000, 0.0000000000e+000,
      0.0000000000e+000, 0.0000000000e+000, 0.0000000000e+000, 0.0000000000e+000, 0.0000000000e+000,
      0.0000000000e+000, 0.0000000000e+000, 0.0000000000e+000, 0.0000000000e+000, 0.0000000000e+000,
      0.0000000000e+000, 0.0000000000e+000, 0.0000000000e+000, 0.0000000000e+000, 0.0000000000e+000,
      0.0000000000e+000, 0.0000000000e+000, 0.0000000000e+000, 0.0000000000e+000, 0.0000000000e+000,
      7.5823496445e-005, 4.6139489859e-004, 1.8151560798e-003, 5.0811171532e-003, 1.1142909527e-002,
      2.0677875727e-002, 3.4121163189e-002, 5.1690407097e-002, 7.3533833027e-002, 9.9674701691e-002,
      1.3002252579e-001, 1.6438430548e-001, 2.0247590542e-001, 2.4393314123e-001, 2.8832298517e-001,
      3.3515489101e-001, 3.8389211893e-001, 4.3396294117e-001, 4.8477154970e-001, 5.3570991755e-001,
      5.8616840839e-001, 6.3554745913e-001, 6.8326860666e-001, 7.2878581285e-001, 7.7159661055e-001,
      8.1125342846e-001, 8.4737491608e-001, 8.7965691090e-001, 9.0788388252e-001, 9.3194031715e-001,
      9.5182150602e-001, 9.6764522791e-001, 9.7966271639e-001, 9.8827010393e-001, 9.9401944876e-001,
      9.9763011932e-001, 1.0000000000e+000 ]

    # I took this from
    # https://www.ecmwf.int/en/forecasts/documentation-and-support/137-model-levels.
    # It's highly likely that I screwed some of the numbers up, but I
    # was kind of careful.
    pv137 = [ 0.000000, 2.000365, 3.102241, 4.666084, 6.827977, 9.746966, 13.605424, 18.608931,
        24.985718, 32.985710, 42.879242, 54.955463, 69.520576, 86.895882, 107.415741, 131.425507,
        159.279404, 191.338562, 227.968948, 269.539581, 316.420746, 368.982361, 427.592499,
        492.616028, 564.413452, 643.339905, 729.744141, 823.967834, 926.344910, 1037.201172,
        1156.853638, 1285.610352, 1423.770142, 1571.622925, 1729.448975, 1897.519287, 2076.095947,
        2265.431641, 2465.770508, 2677.348145, 2900.391357, 3135.119385, 3381.743652, 3640.468262,
        3911.490479, 4194.930664, 4490.817383, 4799.149414, 5119.895020, 5452.990723, 5798.344727,
        6156.074219, 6526.946777, 6911.870605, 7311.869141, 7727.412109, 8159.354004, 8608.525391,
        9076.400391, 9562.682617, 10065.978516, 10584.631836, 11116.662109, 11660.067383, 12211.547852,
        12766.873047, 13324.668945, 13881.331055, 14432.139648, 14975.615234, 15508.256836, 16026.115234,
        16527.322266, 17008.789063, 17467.613281, 17901.621094, 18308.433594, 18685.718750, 19031.289063,
        19343.511719, 19620.042969, 19859.390625, 20059.931641, 20219.664063, 20337.863281, 20412.308594,
        20442.078125, 20425.718750, 20361.816406, 20249.511719, 20087.085938, 19874.025391, 19608.572266,
        19290.226563, 18917.460938, 18489.707031, 18006.925781, 17471.839844, 16888.687500, 16262.046875,
        15596.695313, 14898.453125, 14173.324219, 13427.769531, 12668.257813, 11901.339844, 11133.304688,
        10370.175781, 9617.515625, 8880.453125, 8163.375000, 7470.343750, 6804.421875, 6168.531250,
        5564.382813, 4993.796875, 4457.375000, 3955.960938, 3489.234375, 3057.265625, 2659.140625,
        2294.242188, 1961.500000, 1659.476563, 1387.546875, 1143.250000, 926.507813, 734.992188,
        568.062500, 424.414063, 302.476563, 202.484375, 122.101563, 62.781250, 22.835938,
        3.757813, 0.000000, 0.000000, 0.000000, 0.000000, 0.000000, 0.000000, 0.000000, 0.000000, 0.000000,
        0.000000, 0.000000, 0.000000, 0.000000, 0.000000, 0.000000, 0.000000, 0.000000, 0.000000, 0.000000,
        0.000000, 0.000000, 0.000000, 0.000000, 0.000000, 0.000000, 0.000000, 0.000000, 0.000000,
        0.000000, 0.000000, 0.000000, 0.000000, 0.000000, 0.000000, 0.000000, 0.000000,
        0.000000, 0.000000, 0.000000, 0.000000, 0.000000, 0.000000, 0.000000, 0.000000,
        0.000000, 0.000000, 0.000000, 0.000000, 0.000000, 0.000000, 0.000000, 0.000000,
        0.000000, 0.000000, 0.000000, 0.000000, 0.000000, 0.000007, 0.000024, 0.000059,
        0.000112, 0.000199, 0.000340, 0.000562, 0.000890, 0.001353, 0.001992, 0.002857,
        0.003971, 0.005378, 0.007133, 0.009261, 0.011806, 0.014816, 0.018318, 0.022355,
        0.026964, 0.032176, 0.038026, 0.044548, 0.051773, 0.059728, 0.068448, 0.077958,
        0.088286, 0.099462, 0.111505, 0.124448, 0.138313, 0.153125, 0.168910, 0.185689,
        0.203491, 0.222333, 0.242244, 0.263242, 0.285354, 0.308598, 0.332939, 0.358254,
        0.384363, 0.411125, 0.438391, 0.466003, 0.493800, 0.521619, 0.549301, 0.576692,
        0.603648, 0.630036, 0.655736, 0.680643, 0.704669, 0.727739, 0.749797, 0.770798,
        0.790717, 0.809536, 0.827256, 0.843881, 0.859432, 0.873929, 0.887408, 0.899900,
        0.911448, 0.922096, 0.931881, 0.940860, 0.949064, 0.956550, 0.963352, 0.969513,
        0.975078, 0.980072, 0.984542, 0.988500, 0.991984, 0.995003, 0.997630, 1.000000 ]

    levelSize = len(ts)
    if levelSize == 60:
        pv = pv60
    elif levelSize == 137:
        pv = pv137
    A = pv[0:levelSize+1]
    B = pv[levelSize+1:]

    Ph_levplusone = A[levelSize] + (B[levelSize]*sp)

    #Integrate up into the atmosphere from lowest level
    for lev, t_level, q_level in zip(range(levelSize, 0, -1), ts[::-1], qs[::-1]):
        #lev is the level number 1-60, we need a corresponding index into ts and qs
        ilevel = levelSize - lev

        #compute moist temperature
        t_level = t_level*(1 + 0.609133*q_level)

        #compute the pressures (on half-levels)
        Ph_lev = A[lev-1] + (B[lev-1] * sp)

        pressurelvs[ilevel] = Ph_lev

        if lev == 1:
            dlogP = np.log(Ph_levplusone/0.1)
            alpha = np.log(2)
        else:
            dlogP = np.log(Ph_levplusone/Ph_lev)
            dP = Ph_levplusone - Ph_lev
            alpha = 1 - ((Ph_lev/dP)*dlogP)

        TRd = t_level*Rd

        # z_f is the geopotential of this full level
        # integrate from previous (lower) half-level z_h to the full level
        z_f = z_h + TRd*alpha

        #Convert geopotential to height
        heighttoreturn[ilevel] = z_f / 9.80665

        # z_h is the geopotential of 'half-levels'
        # integrate z_h to next half level
        z_h += TRd * dlogP

        Ph_levplusone = Ph_lev

    return heighttoreturn, pressurelvs


def round_date(date, precision):
    # First try rounding up
    # Timedelta since the beginning of time
    datedelta = datetime.datetime.min - date
    # Round that timedelta to the specified precision
    rem = datedelta % precision
    # Add back to get date rounded up
    round_up = date + rem

    # Next try rounding down
    datedelta = date - datetime.datetime.min
    rem = datedelta % precision
    round_down = date - rem

    # It's not the most efficient to calculate both and then choose, but
    # it's clear, and performance isn't critical here.
    up_diff = round_up - date
    down_diff = date - round_down

    return round_up if up_diff < down_diff else round_down


def class_to_dataset(classname):
    """
    As far as I can figure, ECMWF makes you specify both parameters when making
    a query. So to make it as painless as possible, this function can
    automatically deduce the "dataset" field from the "class" field.
    """
    if classname == 'ei':
        return 'interim'
    if classname == 'ea':
        return 'era5'
    raise ValueError(f'Unknown class name {repr(classname)}')


def get_from_ecmwf(lat_min, lat_max, lat_step, lon_min, lon_max, lon_step,
                   time, out, classname):
    try:
        ecmwfapi
    except NameError:
        raise ecmwfapi_error

    server = ecmwfapi.ECMWFDataServer()

    corrected_date = round_date(time, datetime.timedelta(hours=6))

    maxlv = class_to_maxlv(classname)

    server.retrieve({
        "class": classname, # ERA-Interim
        'dataset': class_to_dataset(classname),
        "expver": "1",
        # They warn me against all, but it works well
        "levelist": 'all',
        "levtype": "ml", # Model levels
        "param": "lnsp/q/z/t", # Necessary variables
        "stream": "oper",
        #date: Specify a single date as "2015-08-01" or a period as "2015-08-01/to/2015-08-31".
        "date": datetime.datetime.strftime(corrected_date, "%Y-%m-%d"),
        "type": "an",        #type: Use an (analysis) unless you have a particular reason to use fc (forecast).
        #time: With type=an, time can be any of "00:00:00/06:00:00/12:00:00/18:00:00".  With type=fc, time can be any of "00:00:00/12:00:00",
        "time": datetime.datetime.strftime(corrected_date, "%H:%M:%S"),
        "step": "0",        #step: With type=an, step is always "0". With type=fc, step can be any of "3/6/9/12".
        "grid": f'{lat_step}/{lon_step}',    #grid: Only regular lat/lon grids are supported.
        #'grid': 'av',
        "area": f'{lat_max}/{lon_min}/{lat_min}/{lon_max}',    #area: N/W/S/E
        "format": "netcdf",
        "resol": "av",
        "target": out,    #target: the name of the output file.
    })


def fetch_era_type(lats, lons, time, classname):
    lat_min = np.min(lats)
    lat_max = np.max(lats)
    lon_min = np.min(lons)
    lon_max = np.max(lons)
    lat_res = 0.2
    lon_res = 0.2

    with tempfile.NamedTemporaryFile() as f:
        get_from_ecmwf(
                lat_min, lat_max, lat_res, lon_min, lon_max, lon_res, time,
                f.name, classname)
        return load(f.name)


def fetch_era_interim(lats, lons, time):
    return fetch_era_type(lats, lons, time, era_interim_classname)


def fetch_era5(lats, lons, time):
    return fetch_era_type(lats, lons, time, era5_classname)


def load(fname):
    with scipy.io.netcdf.netcdf_file(fname, 'r', maskandscale=True) as f:
        # 0,0 to get first time and first level
        z = f.variables['z'][0][0].copy()
        lnsp = f.variables['lnsp'][0][0].copy()
        t = f.variables['t'][0].copy()
        q = f.variables['q'][0].copy()
        lats = f.variables['latitude'][:].copy()
        lons = f.variables['longitude'][:].copy()
    geo_ht, press = calculategeoh(z, lnsp, t, q)
    # ECMWF appears to give me this backwards
    if lats[0] > lats[1]:
        z = z[::-1]
        lnsp = lnsp[::-1]
        t = t[:, ::-1]
        q = q[:, ::-1]
        lats = lats[::-1]
    # Lons is usually ok, but we'll throw in a check to be safe
    if lons[0] > lons[1]:
        z = z[..., ::-1]
        lnsp = lnsp[..., ::-1]
        t = t[..., ::-1]
        q = q[..., ::-1]
        lons = lons[::-1]

    lla = pyproj.Proj(proj='latlong')

    # pyproj gets fussy if the latitude is wrong, plus our interpolator
    # isn't clever enough to pick up on the fact that they are the same
    lons[lons > 180] -= 360


    # TODO: really use k1, k2, k3 from WRF??
    return reader.import_grids(
            # We pass as lons, lats because that's how pyproj likes it
            lons, lats, press, t, q, geo_ht, wrf.k1, wrf.k2, wrf.k3,
            projection=lla, humidity_type='q')


def wm_nodes(fname):
    with scipy.io.netcdf.netcdf_file(fname, 'r', maskandscale=True) as f:
        lats = f.variables['latitude'][:].copy()
        lons = f.variables['longitude'][:].copy()

    latgrid, longrid = np.meshgrid(lats, lons, indexing='ij')
    return latgrid, longrid