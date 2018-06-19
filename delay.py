"""Compute the delay from a point to the transmitter.

Dry and hydrostatic delays are calculated in separate functions.
Currently we take samples every _step meters, which causes either
inaccuracies or inefficiencies, and we no longer can integrate to
infinity. We could develop a more advanced integrator to deal with these
issues, and probably I will. It goes pretty quickly right now, though.
"""


import multiprocessing
import numpy
import progressbar
import scipy.integrate as integrate
import util


# Step in meters to use when integrating
_step = 15


class Zenith:
    """Special value indicating a look vector of "zenith"."""
    pass


def _common_delay(weather, lat, lon, height, look_vec, rnge):
    """Perform computation common to hydrostatic and dry delay."""
    position = util.lla2ecef(lat, lon, height)
    if look_vec is not Zenith:
        corrected_lv = look_vec
    else:
        corrected_lv = numpy.array((util.cosd(lat)*util.cosd(lon),
                                    util.cosd(lat)*util.sind(lon),
                                    util.sind(lat)))
    unit_look_vec = corrected_lv / numpy.linalg.norm(corrected_lv)
    t_points = numpy.linspace(0, rnge, rnge / _step)

    wheres = numpy.zeros((t_points.size, 3))
    for i in range(t_points.size):
        wheres[i][:] = position + unit_look_vec * t_points[i]

    return t_points, wheres


def _work(l):
    """Worker function for integrating delay in a thread."""
    weather, lats, lons, hts, i, j, k = l
    big = 15000
    return (i, j, k,
            hydrostatic_delay(weather, lats[j], lons[k], hts[i],
                              Zenith, big),
            dry_delay(weather, lats[j], lons[k], hts[i], Zenith,
                      big))


def make_lv_range(earth_position, satellite_position):
    """Calculate the look vector and range from satellite position.

    We're given the position on the ground and of the satellite, both in
    lat, lon, ht. From this we calculate the look vector as needed by
    the delay functions. We also calculate the length of the vector,
    i.e., the range for delay.
    """
    earth_ecef = util.lla2ecef(*earth_position)
    satellite_ecef = util.lla2ecef(*satellite_position)
    vec = satellite_ecef - earth_ecef
    return (vec, numpy.linalg.norm(vec))


def _find_e(temp, rh):
    """Calculate partial pressure of water vapor."""
    # We have two possible ways to calculate partial pressure of water
    # vapor. There's the equation from Hanssen, and there's the
    # equations from TRAIN. I don't know which is better.

    # Hanssen: (of course, L, latent heat, isn't perfectly accurate.)
    # e_0 = 611.
    # T_0 = 273.16
    # L = 2.5e6
    # R_v = 461.495
    # e_s = e_0*numpy.exp(L/R_v * (1/T_0 - 1/temp))
    # e = e_s * rh / 100

    # From TRAIN:
    # Could not find the wrf used equation as they appear to be
    # mixed with latent heat etc. Istead I used the equations used
    # in ERA-I (see IFS documentation part 2: Data assimilation
    # (CY25R1)). Calculate saturated water vapour pressure (svp) for
    # water (svpw) using Buck 1881 and for ice (swpi) from Alduchow
    # and Eskridge (1996) euation AERKi
    svpw = (6.1121
            * numpy.exp((17.502*(temp - 273.16))/(240.97 + temp - 273.16)))
    svpi = (6.1121
            * numpy.exp((22.587*(temp - 273.16))/(273.86 + temp - 273.16)))
    tempbound1 = 273.16 # 0
    tempbound2 = 250.16 # -23

    svp = svpw
    wgt = (temp - tempbound2)/(tempbound1 - tempbound2)
    svp = svpi + (svpw - svpi)*wgt**2
    ix_bound1 = temp > tempbound1
    svp[ix_bound1] = svpw[ix_bound1]
    ix_bound2 = temp < tempbound2
    svp[ix_bound2] = svpi[ix_bound2]

    e = rh/100 * svp * 100

    return e


def dry_delay(weather, lat, lon, height, look_vec, rnge):
    """Compute dry delay along the look vector."""
    t_points, wheres = _common_delay(weather, lat, lon, height, look_vec, rnge)

    temp = weather.temperature(wheres)
    rh = weather.rel_humid(wheres)

    # e, the partial pressure of water vapor, is the value we seek
    e = _find_e(temp, rh)

    delay = (weather.k2*e/temp + weather.k3*e/temp**2)

    delay[numpy.isnan(delay)] = 0

    return numpy.trapz(delay, t_points)


def hydrostatic_delay(weather, lat, lon, height, look_vec, rnge):
    """Compute hydrostatic delay along the look vector."""
    t_points, wheres = _common_delay(weather, lat, lon, height, look_vec, rnge)

    temp = weather.temperature(wheres)
    p = weather.pressure(wheres)

    delay = weather.k1*p/temp

    delay[numpy.isnan(delay)] = 0

    return numpy.trapz(delay, t_points)


def delay_over_area(weather, lat_min, lat_max, lat_res, lon_min, lon_max,
                    lon_res, ht_min, ht_max, ht_res):
    """Calculate (in parallel) the delays over an area."""
    lats = numpy.arange(lat_min, lat_max, lat_res)
    lons = numpy.arange(lon_min, lon_max, lon_res)
    hts = numpy.arange(ht_min, ht_max, ht_res)
    out = numpy.zeros((hts.size, lats.size, lons.size),
                      dtype=[('hydro', 'float64'), ('dry', 'float64')])
    with multiprocessing.Pool() as pool:
        jobs = ((weather, lats, lons, hts, i, j, k)
                for i in range(hts.size)
                for j in range(lats.size)
                for k in range(lons.size))
        num_jobs = hts.size * lats.size * lons.size
        answers = pool.imap_unordered(_work, jobs, chunksize=10)
        bar = progressbar.progressbar(answers,
                                      widgets=[progressbar.Bar(), ' ',
                                               progressbar.ETA()],
                                      max_value=num_jobs)
        for result in bar:
            i, j, k, hydro_delay, dry_delay = result
            out[i][j][k] = (hydro_delay, dry_delay)
    return out
