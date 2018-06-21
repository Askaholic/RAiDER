"""Compute the delay from a point to the transmitter.

Dry and hydrostatic delays are calculated in separate functions.
Currently we take samples every _step meters, which causes either
inaccuracies or inefficiencies, and we no longer can integrate to
infinity. We could develop a more advanced integrator to deal with these
issues, and probably I will. It goes pretty quickly right now, though.
"""


from osgeo import gdal
import multiprocessing
import numpy
import progressbar
import scipy.integrate as integrate
import util


# Step in meters to use when integrating
_step = 15


class Zenith:
    """Special value indicating a look vector of "zenith"."""
    def __init__(self, rnge):
        self.rnge = rnge


def _common_delay(weather, lat, lon, height, look_vec):
    """Perform computation common to hydrostatic and dry delay."""
    position = util.lla2ecef(lat, lon, height)
    if isinstance(look_vec, Zenith):
        rnge = look_vec.rnge
        look_vec = numpy.array((util.cosd(lat)*util.cosd(lon),
                                util.cosd(lat)*util.sind(lon), util.sind(lat)))
        l = numpy.linalg.norm(look_vec)
        look_vec /= l
        look_vec *= rnge

    rnge = numpy.linalg.norm(look_vec)
    look_vec /= numpy.linalg.norm(look_vec)

    t_points = numpy.linspace(0, rnge, rnge / _step)

    wheres = numpy.zeros((t_points.size, 3))
    for i in range(t_points.size):
        wheres[i][:] = position + look_vec * t_points[i]

    return t_points, wheres


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


def dry_delay(weather, lat, lon, height, look_vec):
    """Compute dry delay along the look vector."""
    t_points, wheres = _common_delay(weather, lat, lon, height, look_vec)

    dry_delays = weather.dry_delay(wheres)

    return numpy.trapz(dry_delays, t_points)


def hydrostatic_delay(weather, lat, lon, height, look_vec):
    """Compute hydrostatic delay along the look vector."""
    t_points, wheres = _common_delay(weather, lat, lon, height, look_vec)

    delay = weather.hydrostatic_delay(wheres)

    return numpy.trapz(delay, t_points)


def delay_over_area(weather, lat_min, lat_max, lat_res, lon_min, lon_max,
                    lon_res, ht_min, ht_max, ht_res):
    """Calculate (in parallel) the delays over an area."""
    lats = numpy.arange(lat_min, lat_max, lat_res)
    lons = numpy.arange(lon_min, lon_max, lon_res)
    hts = numpy.arange(ht_min, ht_max, ht_res)
    # It's the cartesian product (thanks StackOverflow)
    llas = numpy.array(numpy.meshgrid(lats, lons, hts)).T.reshape(-1,3)
    return delay_from_grid(weather, llas, Zenith)


def _delay_from_grid_work(l):
    """Worker function for integrating delay in a thread."""
    weather, llas, craft, i = l
    lat, lon, ht = llas[i]
    if not isinstance(craft, Zenith):
        position = util.lla2ecef(lat, lon, ht)
        look_vec = craft - position
    else:
        look_vec = Zenith(15000)
    hydro = hydrostatic_delay(weather, lat, lon, ht, look_vec)
    dry = dry_delay(weather, lat, lon, ht, look_vec)
    return (i, hydro, dry)


def delay_from_grid(weather, llas, craft):
    out = numpy.zeros((llas.size, 2))
    with multiprocessing.Pool() as pool:
        jobs = ((weather, llas, craft, i) for i in range(llas.shape[0]))
        answers = pool.imap_unordered(_delay_from_grid_work, jobs,
                                      chunksize=100)
        bar = progressbar.progressbar(answers,
                                      widgets=[progressbar.Bar(), ' ',
                                               progressbar.ETA()],
                                      max_value=llas.shape[0])
        for result in bar:
            i, hydro_delay, dry_delay = result
            out[i] = (hydro_delay, dry_delay)
    return out



def nonparallel(weather, llas, craft):
    out = numpy.zeros((llas.shape[0], 2))
    jobs = ((weather, llas, craft, i) for i in range(llas.shape[0]))
    answers = map(_delay_from_grid_work, jobs)
    bar = progressbar.progressbar(answers,
                                  widgets=[progressbar.Bar(), ' ',
                                           progressbar.AdaptiveETA(samples=100)],
                                  max_value=llas.shape[0])
    for result in bar:
        i, hydro_delay, dry_delay = result
        out[i][:] = (hydro_delay, dry_delay)
    return out


def delay_from_files(weather, lat, lon, ht):
    lats = gdal.Open(lat).ReadAsArray()
    lons = gdal.Open(lon).ReadAsArray()
    hts = gdal.Open(ht).ReadAsArray()
    llas = numpy.stack((lats.flatten(), lons.flatten(), hts.flatten()), axis=1)
    #return delay_from_grid(weather, llas, Zenith(15000))
    return nonparallel(weather, llas, Zenith(15000))
