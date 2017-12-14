import numpy as np
import os
import re
import sqlite3
from collections import OrderedDict
import time
import gc
from lsst.utils import getPackageDir
from lsst.sims.utils import trixelFromHtmid, getAllTrixels
from lsst.sims.utils import levelFromHtmid, halfSpaceFromRaDec
from lsst.sims.utils import angularSeparation, ObservationMetaData
from lsst.sims.utils import arcsecFromRadians
from lsst.sims.catUtils.utils import _baseLightCurveCatalog
from lsst.sims.utils import _pupilCoordsFromRaDec
from lsst.sims.coordUtils import chipNameFromPupilCoordsLSST
from lsst.sims.coordUtils import pixelCoordsFromPupilCoords
from lsst.sims.coordUtils import lsst_camera

from lsst.sims.catalogs.decorators import compound, cached
from lsst.sims.photUtils import BandpassDict, Sed, calcSNR_m5
from lsst.sims.photUtils import PhotometricParameters
from lsst.sims.catUtils.mixins import VariabilityStars, AstrometryStars
from lsst.sims.catUtils.mixins import VariabilityGalaxies, AstrometryGalaxies
from lsst.sims.catUtils.mixins import CameraCoordsLSST, PhotometryBase
from lsst.sims.catUtils.mixins import ParametrizedLightCurveMixin
from lsst.sims.catUtils.mixins import create_variability_cache

from lsst.sims.catUtils.baseCatalogModels import StarObj, GalaxyAgnObj
from sqlalchemy.sql import select, func, text
from lsst.sims.catalogs.db import ChunkIterator

__all__ = ["AlertDataGenerator",
           "AlertStellarVariabilityCatalog",
           "AlertAgnVariabilityCatalog",
           "_baseAlertCatalog",
           "StellarAlertDBObj",
           "AgnAlertDBObj",
           "StellarAlertDBObjMixin"]

class StellarAlertDBObjMixin(object):
    """
    Mimics StarObj class, except it allows you to directly query
    all objects in a trixel specified by an htmid.
    """
    def query_columns_htmid(self, colnames=None, chunk_size=None,
                            obs_metadata=None, constraint=None,
                            limit=None, htmid=None):
        """Execute a query from the primary catsim database

        Execute a query, taking advantage of the spherical geometry library and
        htmid indexes on all catalog tables in the UW catsim database

        **Parameters**

            * colnames : list or None
              a list of valid column names, corresponding to entries in the
              `columns` class attribute.  If not specified, all columns are
              queried.
            * chunk_size : int (optional)
              if specified, then return an iterator object to query the database,
              each time returning the next `chunk_size` elements.  If not
              specified, all matching results will be returned.
            * obs_metadata : object (optional)
              This will be ignored
            * constraint : str (optional)
              a string which is interpreted as SQL and used as a predicate on the query
            * limit : int (optional)
              limits the number of rows returned by the query
            * htmid is the htmid to be queried

        **Returns**

            * result : list or iterator
              If chunk_size is not specified, then result is a list of all
              items which match the specified query.  If chunk_size is specified,
              then result is an iterator over lists of the given size.
        """

        # find the minimum and maximum htmid
        # (level=21 since that is what is implemented
        # on fatboy) that we are asking for
        #
        # Note that sqlalchemy does not like np.int64
        # as a data type
        current_level = levelFromHtmid(htmid)
        n_bits_off = 2*(21-current_level)
        htmid_min = int(htmid << n_bits_off)
        htmid_max = int((htmid+1) << n_bits_off)

        query = self._get_column_query(colnames)

        #add spatial constraints to query.

        #Hint sql engine to seek on htmid
        if not self.tableid.endswith('forceseek'):
            query = query.with_hint(self.table, ' WITH(FORCESEEK)', 'mssql')

        #SQL is not case sensitive but python is:
        if 'htmID' in self.columnMap:
            htmidName = 'htmID'
        elif 'htmid' in self.columnMap:
            htmidName = 'htmid'
        else:
            htmidName = 'htmId'

        #Range join on htmid ranges
        query = query.filter(self.table.c[htmidName].between(htmid_min, htmid_max))

        if constraint is not None:
            query = query.filter(text(constraint))

        if limit is not None:
            query = query.limit(limit)

        return ChunkIterator(self, query, chunk_size)

class StellarAlertDBObj(StellarAlertDBObjMixin, StarObj):
    pass

class AgnAlertDBObj(GalaxyAgnObj):
    """
    Mimics GalaxyAgnObj class, except it allows you to directly query
    all objects in a trixel specified by an htmid.
    """

    columns = [('htmid', 0, np.int64),
               ('galtileid', None, np.int64),
               ('galid', None, str, 30),
               ('componentra', 'agnra*PI()/180.'),
               ('componentdec', 'agndec*PI()/180.'),
               #: This is actually a problem with the stored procedure.
               #: We need to be able to map columns other than
               #: just ra/dec to raJ2000/decJ2000.  This gets
               #: important when we start perturbing the three galaxy components
               ('raJ2000', 'ra'),
               ('decJ2000', 'dec'),
               ('magNorm', 'magnorm_agn'),
               ('magNormAgn', 'magnorm_agn'),
               ('sedFilename', 'sedname_agn', str, 40),
               ('sedFilenameAgn', 'sedname_agn', str, 40),
               ('variabilityParameters', 'varParamStr', str, 256),
               ('lsst_u', 'u_ab'),
               ('lsst_g', 'g_ab'),
               ('lsst_r', 'r_ab'),
               ('lsst_i', 'i_ab'),
               ('lsst_z', 'z_ab'),
               ('lsst_y', 'y_ab')]


    def query_columns_htmid(self, colnames=None, chunk_size=None,
                            obs_metadata=None, constraint=None,
                            limit=None, htmid=None):
        """Execute a query from the primary catsim database

        Execute a query, taking advantage of the spherical geometry library and
        htmid indexes on all catalog tables in the UW catsim database

        **Parameters**

            * colnames : list or None
              a list of valid column names, corresponding to entries in the
              `columns` class attribute.  If not specified, all columns are
              queried.
            * chunk_size : int (optional)
              if specified, then return an iterator object to query the database,
              each time returning the next `chunk_size` elements.  If not
              specified, all matching results will be returned.
            * obs_metadata : object (optional)
              This will be ignored
            * constraint : str (optional)
              a string which is interpreted as SQL and used as a predicate on the query
            * limit : int (optional)
              limits the number of rows returned by the query
            * htmid is the htmid to be queried

        **Returns**

            * result : list or iterator
              If chunk_size is not specified, then result is a list of all
              items which match the specified query.  If chunk_size is specified,
              then result is an iterator over lists of the given size.
        """

        trixel = trixelFromHtmid(htmid)
        ra_0, dec_0 = trixel.get_center()
        new_obs = ObservationMetaData(pointingRA=ra_0, pointingDec=dec_0, boundType='circle',
                                      boundLength=trixel.get_radius()+0.1)

        self._queried_trixel = trixel
        self._queried_htmid_level = levelFromHtmid(htmid)

        return self.query_columns(colnames=colnames, chunk_size=chunk_size,
                                  obs_metadata=new_obs, constraint=constraint,
                                  limit=limit)

    def _final_pass(self, results):
        """Modify the results of raJ2000 and decJ2000 to be in radians.

        Also filter the results so that any objects outside of the
        trixel specified in query_columns_htmid are returned with
        htmid=0.

        **Parameters**

            * results : Structured array of results from query

        **Returns**

            * results : Modified structured array

        """

        if hasattr(self, '_queried_trixel'):
            htmid= self._queried_trixel.htmid
            htmid_21 = htmid << 2*(21-self._queried_htmid_level)
            assert levelFromHtmid(htmid_21) == 21
            contains_arr = self._queried_trixel.contains(results['raJ2000'], results['decJ2000'])
            results['htmid'] = np.where(contains_arr, htmid_21, 0)

        results['raJ2000'] = np.radians(results['raJ2000'])
        results['decJ2000'] = np.radians(results['decJ2000'])
        return results


class _baseAlertCatalog(PhotometryBase, CameraCoordsLSST, _baseLightCurveCatalog):

    column_outputs = ['htmid', 'uniqueId', 'raICRS', 'decICRS',
                      'flux', 'SNR', 'dflux',
                      'chipNum', 'xPix', 'yPix']

    default_formats = {'f':'%.4g'}

    default_columns = [('properMotionRa', 0.0, float),
                       ('properMotionDec', 0.0, float),
                       ('parallax', 0.0, float)]

    def iter_catalog_chunks(self, chunk_size=None, query_cache=None, column_cache=None):
        """
        Returns an iterator over chunks of the catalog.

        Parameters
        ----------
        chunk_size : int, optional, defaults to None
            the number of rows to return from the database at a time. If None,
            returns the entire database query in one chunk.

        query_cache : iterator over database rows, optional, defaults to None
            the result of calling db_obj.query_columns().  If query_cache is not
            None, this method will iterate over the rows in query_cache and produce
            an appropriate InstanceCatalog. DO NOT set to non-None values
            unless you know what you are doing.  It is an optional
            input for those who want to repeatedly examine the same patch of sky
            without actually querying the database over and over again.  If it is set
            to None (default), this method will handle the database query.

        column_cache : a dict that will be copied over into the catalogs self._column_cache.
            Should be left as None, unless you know what you are doing.
        """

        if query_cache is None:
            # Call the originalversion of iter_catalog defined in the
            # InstanceCatalog class.  This version of iter_catalog includes
            # the call to self.db_obj.query_columns, which the user would have
            # used to generate query_cache.
            for line in InstanceCatalog.iter_catalog_chunks(self, chunk_size=chunk_size):
                yield line
        else:
            # Otherwise iterate over the query cache
            transform_keys = list(self.transformations.keys())
            for chunk in query_cache:
                self._set_current_chunk(chunk, column_cache=column_cache)
                chunk_cols = [self.transformations[col](self.column_by_name(col))
                              if col in transform_keys else
                              self.column_by_name(col)
                              for col in self.iter_column_names()]
                if not hasattr(self, '_chunkColMap_output'):
                    self._chunkColMap_output = dict([(col, i) for i, col in enumerate(self.iter_column_names())])
                yield chunk_cols, self._chunkColMap_output

        self._column_cache = {}
        self._current_chunk = None

    @cached
    def get_chipName(self):
        if len(self.column_by_name('uniqueId')) == 0:
            return np.array([])
        raise RuntimeError("Should not get this far in get_chipName")

    @compound('x_pupil', 'y_pupil')
    def get_pupilFromSky(self):
        if len(self.column_by_name('uniqueId')) == 0:
            return np.array([[], []])
        raise RuntimeError("Should not get this far in get_pupilFromSky")

    @cached
    def get_chipNum(self):
        """
        Concatenate the digits in 'R:i,j S:m,n' to make the chip number ijmn
        """
        chip_name = self.column_by_name('chipName')
        return np.array([int(''.join(re.findall(r'\d+', name))) if name is not None else 0
                        for name in chip_name])

    @compound('xPix', 'yPix')
    def get_pixelCoordinates(self):
        xPup = self.column_by_name('x_pupil')
        yPup = self.column_by_name('y_pupil')
        chipName = self.column_by_name('chipName')
        xpix, ypix = pixelCoordsFromPupilCoords(xPup, yPup, chipName=chipName,
                                                camera=lsst_camera(),
                                                includeDistortion=True)
        return np.array([xpix, ypix])


    @compound('delta_umag', 'delta_gmag', 'delta_rmag',
              'delta_imag', 'delta_zmag', 'delta_ymag')
    def get_deltaMagAvro(self):
        ra = self.column_by_name('raJ2000')
        if len(ra)==0:
            return np.array([[],[],[],[],[],[]])

        raise RuntimeError("Should not have gotten this far in delta mag getter")


    @compound('lsst_u','lsst_g','lsst_r','lsst_i','lsst_z','lsst_y')
    def get_lsst_magnitudes(self):
        """
        getter for LSST stellar magnitudes
        """

        magnitudes = np.array([self.column_by_name('quiescent_lsst_u'),
                               self.column_by_name('quiescent_lsst_g'),
                               self.column_by_name('quiescent_lsst_r'),
                               self.column_by_name('quiescent_lsst_i'),
                               self.column_by_name('quiescent_lsst_z'),
                               self.column_by_name('quiescent_lsst_y')])

        delta = np.array([self.column_by_name('delta_umag'),
                          self.column_by_name('delta_gmag'),
                          self.column_by_name('delta_rmag'),
                          self.column_by_name('delta_imag'),
                          self.column_by_name('delta_zmag'),
                          self.column_by_name('delta_ymag')])
        magnitudes += delta

        return magnitudes

    @compound('mag', 'dmag', 'quiescent_mag')
    def get_alertPhotometry(self):
        mag = self.column_by_name('lsst_%s' % self.obs_metadata.bandpass)
        quiescent_mag = self.column_by_name('quiescent_lsst_%s' % self.obs_metadata.bandpass)
        dmag = mag - quiescent_mag

        return np.array([mag, dmag, quiescent_mag])

    @compound('flux', 'dflux', 'SNR')
    def get_alertFlux(self):
        quiescent_mag = self.column_by_name('quiescent_mag')
        mag = self.column_by_name('mag')
        if not hasattr(self, '_dummy_sed'):
            self._dummy_sed = Sed()
        if not hasattr(self, 'lsstBandpassDict'):
            self.lsstBandpassDict = BandpassDict.loadTotalBandpassesFromFiles()
        if not hasattr(self, 'photParams'):
            self.photParams = PhotometricParameters()
        if not hasattr(self, '_gamma'):
            self._gamma = None

        quiescent_flux = self._dummy_sed.fluxFromMag(quiescent_mag)
        flux = self._dummy_sed.fluxFromMag(mag)
        dflux = flux - quiescent_flux

        snr_tot, gamma = calcSNR_m5(mag, self.lsstBandpassDict[self.obs_metadata.bandpass],
                                    self.obs_metadata.m5[self.obs_metadata.bandpass],
                                    self.photParams, gamma=self._gamma)

        if self._gamma is None:
            self._gamma = gamma

        return np.array([flux, dflux, snr_tot])


class AlertStellarVariabilityCatalog(_baseAlertCatalog,
                                     VariabilityStars,
                                     AstrometryStars):

    @compound('quiescent_lsst_u', 'quiescent_lsst_g', 'quiescent_lsst_r',
              'quiescent_lsst_i', 'quiescent_lsst_z', 'quiescent_lsst_y')
    def get_quiescent_lsst_magnitudes(self):
        return np.array([self.column_by_name('umag'), self.column_by_name('gmag'),
                         self.column_by_name('rmag'), self.column_by_name('imag'),
                         self.column_by_name('zmag'), self.column_by_name('ymag')])


class AlertAgnVariabilityCatalog(_baseAlertCatalog,
                                 VariabilityGalaxies,
                                 AstrometryGalaxies):

    @compound('quiescent_lsst_u', 'quiescent_lsst_g', 'quiescent_lsst_r',
              'quiescent_lsst_i', 'quiescent_lsst_z', 'quiescent_lsst_y')
    def get_quiescent_lsst_magnitudes(self):
        return np.array([self.column_by_name('u_ab'), self.column_by_name('g_ab'),
                         self.column_by_name('r_ab'), self.column_by_name('i_ab'),
                         self.column_by_name('z_ab'), self.column_by_name('y_ab')])



class AlertDataGenerator(object):

    def __init__(self,
                 testing=False):

        self._variability_cache = create_variability_cache()
        self._stdout_lock = None
        if not testing:
            plm = ParametrizedLightCurveMixin()
            plm.load_parametrized_light_curves(variability_cache = self._variability_cache)
        self.bp_dict = BandpassDict.loadTotalBandpassesFromFiles()

    def acquire_lock(self):
        """
        If running with multiprocessing, acquire
        the lock.
        """
        if self._stdout_lock is not None:
            self._stdout_lock.acquire()

    def release_lock(self):
        """
        If running with multiprocessing, release
        the lock.
        """
        if self._stdout_lock is not None:
            self._stdout_lock.release()

    def subdivide_obs(self, obs_list, htmid_level=6):
        """
        Take a list of ObservationMetaData and subdivide
        them according to which trixels (see htmModule.py
        in sims_utils) they intersect.

        Parameters
        ----------
        obs_list is a list of ObservationMetaData

        htmid_level is an int denoting the level of
        the HTM mesh you want to use to tile the sky
        (higher htmid_level corresponds to a finer
        tiling).

        Returns
        -------
        Nothing.

        After running this method, this AlertGenerator
        will contain the following data.

        - a list of the htmid of every trixel intersected
        by the fields of view specified in obs_list.  This
        list is accessible from the property
        AlertGenerator.htmid_list

        - a dict mapping each htmid to the ObservationMetaData
        from obs_list that intersect it.  The method
        AlertGenerator.obs_from_htmid(htmid) will return a
        list of all of the ObservationMetaData that intersect
        the trixel specified by htmid.
        """
        t_start = time.time()
        self._trixel_dict = getAllTrixels(htmid_level)
        valid_htmid = []
        for htmid in self._trixel_dict:
            if levelFromHtmid(htmid) == htmid_level:
                valid_htmid.append(htmid)

        #print("made trixel dict")

        obs_list = np.array(obs_list)
        self._obs_list = obs_list
        obs_ra_list = []
        obs_dec_list = []
        halfspace_list = []
        for obs in obs_list:
            obs_ra_list.append(obs.pointingRA)
            obs_dec_list.append(obs.pointingDec)
            hs = halfSpaceFromRaDec(obs.pointingRA,
                                    obs.pointingDec,
                                    obs.boundLength)
            halfspace_list.append(hs)

        obs_ra_list = np.array(obs_ra_list)
        obs_dec_list = np.array(obs_dec_list)
        halfspace_list = np.array(halfspace_list)
        #print("made ra and dec lists")
        self._htmid_dict = {}
        self._htmid_list = []
        n_obs_list = []
        already_assigned = set()
        n_already_assigned = 0
        query_radius = 1.75
        for i_htmid, htmid in enumerate(valid_htmid):
            trixel = self._trixel_dict[htmid]
            ra_c, dec_c = trixel.get_center()
            radius = trixel.get_radius()
            obs_distance = angularSeparation(ra_c, dec_c, obs_ra_list, obs_dec_list)
            valid_obs = np.where(obs_distance<radius+query_radius)
            if len(valid_obs[0])>0:
                final_obs_list = []
                for obs_dex in valid_obs[0]:
                    hs = halfspace_list[obs_dex]
                    obs = obs_list[obs_dex]
                    if hs.contains_trixel(trixel) != 'outside':
                        final_obs_list.append(obs_dex)
                        if obs_dex in already_assigned:
                            n_already_assigned += 1
                        if obs_dex not in already_assigned:
                            already_assigned.add(obs_dex)
                if len(final_obs_list) == 0:
                    continue

                self._htmid_dict[htmid] = np.array(final_obs_list)
                self._htmid_list.append(htmid)
                n_obs_list.append(len(final_obs_list))
            elapsed = time.time()-t_start
            if(i_htmid%1000==0):
                print('    %d took %e; total %e' % (i_htmid+1, elapsed, len(valid_htmid)*elapsed/(i_htmid+1)))

        n_obs_list = np.array(n_obs_list)
        self._htmid_list = np.array(self._htmid_list)
        sorted_dex = np.argsort(-1.0*n_obs_list)
        self._htmid_list = self._htmid_list[sorted_dex]
        print('done subdividing obs list -- %d htmid' %
              len(self._htmid_list))
        #print('min nobs %d median %d max %d' % (n_obs_list.min(), np.median(n_obs_list), n_obs_list.max()))
        n_obs_list = np.sort(n_obs_list)
        print("%d %d %d %d %d" %
              (n_obs_list[0],
               n_obs_list[len(n_obs_list)//4],
               n_obs_list[len(n_obs_list)//2],
               n_obs_list[3*len(n_obs_list)//4],
               n_obs_list[-1]))
        print('n already %d' % n_already_assigned)

    @property
    def htmid_list(self):
        """
        A list of the unique htmid's corresponding to the fields
        of view that need to be queried to generate the alert data
        """
        return self._htmid_list

    def n_obs(self, htmid):
        return len(self._htmid_dict[htmid])

    def obs_from_htmid(self, htmid):
        return self._obs_list[self._htmid_dict[htmid]]

    def output_alert_data(self, conn, data_cache, log_file_name):
        """
        Cache will be keyed first on the obsHistID, then all of the columns
        """
        t_start = time.time()
        cursor = conn.cursor()
        n_rows_0 = cursor.execute('SELECT COUNT(uniqueId) FROM alert_data').fetchall()

        chunk_lengths = np.zeros(len(data_cache))

        for i_cache_tag, cache_tag in enumerate(data_cache):
            obsHistID = int(cache_tag.split('_')[0])
            n_obj = len(data_cache[cache_tag]['uniqueId'])
            chunk_lengths[i_cache_tag] = n_obj

            values = ((int(data_cache[cache_tag]['uniqueId'][i_obj]),
                      obsHistID,
                      data_cache[cache_tag]['xPix'][i_obj],
                      data_cache[cache_tag]['yPix'][i_obj],
                      int(data_cache[cache_tag]['chipNum'][i_obj]),
                      data_cache[cache_tag]['dflux'][i_obj],
                      data_cache[cache_tag]['SNR'][i_obj],
                      np.degrees(data_cache[cache_tag]['raICRS'][i_obj]),
                      np.degrees(data_cache[cache_tag]['decICRS'][i_obj]))
                      for i_obj in range(n_obj))
            cursor.executemany('INSERT INTO alert_data VALUES (?,?,?,?,?,?,?,?,?)', values)
        conn.commit()

        n_rows_1 = cursor.execute('SELECT COUNT(uniqueId) FROM alert_data').fetchall()
        conn.commit()
        n_written = (n_rows_1[0][0]-n_rows_0[0][0])
        #print('    n_written %d time write %e hrs per %e' % (n_written, elapsed, elapsed/n_written))

        chunk_lengths = np.sort(chunk_lengths)

        self.acquire_lock()
        elapsed = (time.time()-t_start)/3600.0
        min_chunk = chunk_lengths.min()
        max_chunk = chunk_lengths.max()
        n_chunks = len(chunk_lengths)
        first_q = chunk_lengths[n_chunks//4]
        third_q = chunk_lengths[(n_chunks*3)//4]
        second_q = chunk_lengths[n_chunks//2]
        with open(log_file_name, 'a') as out_file:
            out_file.write('\n    %d chunk stats %d %d %d %d %d\n' % (os.getpid(), min_chunk,
                           first_q, second_q, third_q, max_chunk))
            out_file.write('    %d chunks\n' % len(chunk_lengths))
            out_file.write('    wrote %d rows in %.2e hrs; per %.2e\n' %
                           (n_written, elapsed, elapsed/n_written))

            print('\n    %d chunk stats %d %d %d %d %d' % (os.getpid(), min_chunk,
                           first_q, second_q, third_q, max_chunk))
            print('    %d chunks' % len(chunk_lengths))
            print('    wrote %d rows in %.2e hrs; per %.2e' %
                               (n_written, elapsed, elapsed/n_written))
        self.release_lock()

        return n_written

    def filter_on_chip_name_then_photometry(self, chunk, column_query,
                                            obs_valid_dex, expmjd_list,
                                            photometry_catalog):
        if 'properMotionRa'in column_query:
            pmra = chunk['properMotionRa']
            pmdec = chunk['properMotionDec']
            px = chunk['parallax']
            vrad = chunk['radialVelocity']
        else:
            pmra = None
            pmdec = None
            px = None
            vrad = None

        #for ii in range(6):
        #    print('dmag %d: %e %e %e' % (ii,dmag_arr[ii].min(),np.median(dmag_arr[ii]),dmag_arr[ii].max()))
        #exit()

        ###################################################################
        # Figure out which sources actually land on an LSST detector during
        # the observations in question
        #
        t_before_chip_name = time.time()
        chip_name_dict = {}

        # time_arr will keep track of which objects appear in which observations;
        # 1 means the object appears; -1 means it does not
        time_arr_transpose = -1*np.ones((len(obs_valid_dex), len(chunk['raJ2000'])),
                                        dtype=int)

        for i_obs, obs_dex in enumerate(obs_valid_dex):
            obs = self._obs_list[obs_dex]
            xPup_list, yPup_list = _pupilCoordsFromRaDec(chunk['raJ2000'], chunk['decJ2000'],
                                                         pm_ra=pmra, pm_dec=pmdec,
                                                         parallax=px, v_rad=vrad,
                                                         obs_metadata=obs)

            chip_name_list = chipNameFromPupilCoordsLSST(xPup_list, yPup_list)

            chip_int_arr = -1*np.ones(len(chip_name_list), dtype=int)
            for i_chip, name in enumerate(chip_name_list):
                if name is not None:
                    chip_int_arr[i_chip] = 1

            valid_obj = np.where(chip_int_arr>0)
            time_arr_transpose[i_obs][valid_obj] = 1
            chip_name_dict[i_obs] = (chip_name_list,
                                     xPup_list,
                                     yPup_list,
                                     valid_obj)

        time_arr = time_arr_transpose.transpose()
        assert len(chip_name_dict) == len(obs_valid_dex)

        ######################################################
        # Calculate the delta_magnitude for all of the sources
        #
        t_before_phot = time.time()

        # only calculate photometry for objects that actually land
        # on LSST detectors

        n_raw_obj = len(chunk)
        valid_photometry = -1*np.ones(n_raw_obj)

        t_before_filter = time.time()
        for i_obs in range(len(obs_valid_dex)):
            name_list, xpup_list, ypup_list, valid_obj = chip_name_dict[i_obs]
            valid_photometry[valid_obj] += 2
        invalid_dex = np.where(valid_photometry<0)
        chunk['varParamStr'][invalid_dex] = 'None'

        photometry_catalog._set_current_chunk(chunk)
        dmag_arr = photometry_catalog.applyVariability(chunk['varParamStr'],
                                                       variability_cache=self._variability_cache,
                                                       expmjd=expmjd_list,).transpose((2,0,1))

        dmag_arr_transpose = dmag_arr.transpose(2,1,0)

        return chip_name_dict, dmag_arr, dmag_arr_transpose, time_arr

    def filter_on_photometry_then_chip_name(self, chunk, column_query,
                                            obs_valid_dex, expmjd_list,
                                            photometry_catalog,
                                            dmag_cutoff):


        photometry_catalog._set_current_chunk(chunk)
        dmag_arr = photometry_catalog.applyVariability(chunk['varParamStr'],
                                                       variability_cache=self._variability_cache,
                                                       expmjd=expmjd_list,).transpose((2,0,1))

        dmag_arr_transpose = dmag_arr.transpose(2,1,0)

        n_raw_obj = len(chunk)
        photometrically_valid = -1*np.ones(n_raw_obj, dtype=int)
        for i_obj in range(n_raw_obj):
            keep_it = False
            for i_filter in range(6):
               if np.abs(dmag_arr_transpose[i_obj][i_filter]).max() >= dmag_cutoff:
                   keep_it = True
                   break
            if keep_it:
                photometrically_valid[i_obj] = 1

        photometrically_valid = np.where(photometrically_valid>=0)

        if 'properMotionRa'in column_query:
            pmra = chunk['properMotionRa'][photometrically_valid]
            pmdec = chunk['properMotionDec'][photometrically_valid]
            px = chunk['parallax'][photometrically_valid]
            vrad = chunk['radialVelocity'][photometrically_valid]
        else:
            pmra = None
            pmdec = None
            px = None
            vrad = None

        #for ii in range(6):
        #    print('dmag %d: %e %e %e' % (ii,dmag_arr[ii].min(),np.median(dmag_arr[ii]),dmag_arr[ii].max()))
        #exit()

        ###################################################################
        # Figure out which sources actually land on an LSST detector during
        # the observations in question
        #
        t_before_chip_name = time.time()
        chip_name_dict = {}

        # time_arr will keep track of which objects appear in which observations;
        # 1 means the object appears; -1 means it does not
        time_arr_transpose = -1*np.ones((len(obs_valid_dex), len(chunk['raJ2000'])),
                                        dtype=int)

        for i_obs, obs_dex in enumerate(obs_valid_dex):
            obs = self._obs_list[obs_dex]
            chip_name_list = np.array([None]*n_raw_obj)
            xPup_list = np.zeros(n_raw_obj, dtype=float)
            yPup_list = np.zeros(n_raw_obj, dtype=float)
            chip_int_arr = -1*np.ones(len(chip_name_list), dtype=int)

            if len(photometrically_valid[0])>0:
                xPup_list_val, yPup_list_val = _pupilCoordsFromRaDec(chunk['raJ2000'][photometrically_valid],
                                                                     chunk['decJ2000'][photometrically_valid],
                                                                     pm_ra=pmra, pm_dec=pmdec,
                                                                     parallax=px, v_rad=vrad,
                                                                     obs_metadata=obs)

                xPup_list[photometrically_valid] = xPup_list_val
                yPup_list[photometrically_valid] = yPup_list_val

                chip_name_list[photometrically_valid] = chipNameFromPupilCoordsLSST(xPup_list_val,
                                                                                    yPup_list_val)

                for i_chip, name in enumerate(chip_name_list):
                    if name is not None:
                        chip_int_arr[i_chip] = 1

            valid_obj = np.where(chip_int_arr>0)
            time_arr_transpose[i_obs][valid_obj] = 1

            chip_name_dict[i_obs] = (chip_name_list,
                                     xPup_list,
                                     yPup_list,
                                     valid_obj)

        time_arr = time_arr_transpose.transpose()
        assert len(chip_name_dict) == len(obs_valid_dex)

        ######################################################
        # Calculate the delta_magnitude for all of the sources
        #
        t_before_phot = time.time()

        # only calculate photometry for objects that actually land
        # on LSST detectors

        return chip_name_dict, dmag_arr, dmag_arr_transpose, time_arr


    def alert_data_from_htmid(self, htmid, dbobj, radius=1.75,
                              dmag_cutoff=0.005,
                              chunk_size=1000, write_every=10000,
                              output_dir='.', output_prefix='',
                              log_file_name=None,
                              photometry_class=None,
                              chunk_cutoff=-1,
                              lock=None):

        htmid_level = levelFromHtmid(htmid)
        if log_file_name is None:
            raise RuntimeError('must specify log_file_name')

        if '_PARAMETRIZED_LC_DMAG_LOOKUP' not in self._variability_cache:
            self._variability_cache['_PARAMETRIZED_LC_DMAG_CUTOFF'] = dmag_cutoff
            self._variability_cache['_PARAMETRIZED_LC_DMAG_LOOKUP'] = {}
            dmag_lookup_file = os.path.join(getPackageDir('sims_data'),
                                            'catUtilsData',
                                            'kplr_dmag_171204.txt')

            with open(dmag_lookup_file, 'r') as in_file:
                for line in in_file:
                    params = line.split()
                    self._variability_cache['_PARAMETRIZED_LC_DMAG_LOOKUP'][int(params[0])] = float(params[1])

        self._stdout_lock = lock
        this_pid = os.getpid()

        t_start = time.time()

        desired_columns = []
        desired_columns.append('simobjid')
        desired_columns.append('variabilityParameters')
        desired_columns.append('varParamStr')
        desired_columns.append('raJ2000')
        desired_columns.append('decJ2000')
        desired_columns.append('properMotionRa')
        desired_columns.append('properMotionDec')
        desired_columns.append('parallax')
        desired_columns.append('radialVelocity')
        desired_columns.append('ebv')
        desired_columns.append('redshift')
        desired_columns.append('htmid')

        if 'umag' in dbobj.columnMap:
            desired_columns.append('umag')
            desired_columns.append('gmag')
            desired_columns.append('rmag')
            desired_columns.append('imag')
            desired_columns.append('zmag')
            desired_columns.append('ymag')
        elif 'u_ab' in dbobj.columnMap:
            desired_columns.append('u_ab')
            desired_columns.append('g_ab')
            desired_columns.append('r_ab')
            desired_columns.append('i_ab')
            desired_columns.append('z_ab')
            desired_columns.append('y_ab')
        else:
            raise RuntimeError('Not sure what quiescent '
                               'LSST magnitudes are called '
                               'in this CatalogDBObject')

        if photometry_class is None:
            raise RuntimeError('Must specify photometry_class')

        if os.path.exists(output_dir) and not os.path.isdir(output_dir):
            raise RuntimeError('%s is not a dir' % output_dir)
        if not os.path.exists(output_dir):
            os.mkdir(output_dir)

        #print('htmid %d' % (htmid))

        dummy_sed = Sed()

        # a dummy call to make sure that the initialization
        # is done before we attempt to parallelize calls
        # to chipNameFromRaDecLSST
        dummy_name = chipNameFromPupilCoordsLSST(0.0, 0.0)

        mag_names = ('u', 'g', 'r', 'i', 'z', 'y')

        photParams = PhotometricParameters()

        # from Table 2 of the overview paper
        obs_mag_cutoff = (23.68, 24.89, 24.43, 24.0, 24.45, 22.60)

        gamma_template = {}
        for i_filter in range(6):
            gamma_template[i_filter] = None

        obs_valid_dex = self._htmid_dict[htmid]
        print('n valid obs %d' % len(obs_valid_dex))

        cat_list = []
        expmjd_list = []
        mag_name_to_int = {'u':0, 'g':1, 'r':2, 'i':3, 'z':4, 'y':5}
        for obs_dex in obs_valid_dex:
            obs = self._obs_list[obs_dex]
            cat = photometry_class(dbobj, obs_metadata=obs)
            cat.lsstBandpassDict =  self.bp_dict
            cat_list.append(cat)
            expmjd_list.append(obs.mjd.TAI)

        expmjd_list = np.array(expmjd_list)
        cat_list = np.array(cat_list)
        sorted_dex = np.argsort(expmjd_list)

        expmjd_list = expmjd_list[sorted_dex]
        cat_list = cat_list[sorted_dex]
        obs_valid_dex = obs_valid_dex[sorted_dex]

        #print('built list')

        available_columns = list(dbobj.columnMap.keys())
        column_query = []
        for col in desired_columns:
            if col in available_columns:
                column_query.append(col)

        n_bits_off = 2*(21-htmid_level)

        data_iter = dbobj.query_columns_htmid(colnames=column_query,
                                              htmid=htmid,
                                              chunk_size=chunk_size)

        #print("time for photometry catalog")

        photometry_catalog = photometry_class(dbobj, self._obs_list[obs_valid_dex[0]],
                                              column_outputs=['lsst_u',
                                                              'lsst_g',
                                                              'lsst_r',
                                                              'lsst_i',
                                                              'lsst_z',
                                                              'lsst_y'])

        #print('chunking')
        i_chunk = 0
        t_chipName = 0.0
        t_before_obj = time.time()

        output_data_cache = {}
        n_rows_cached = 0

        n_obj = 0
        n_actual_obj = 0
        n_time_last = 0
        n_rows = 0

        db_name = os.path.join(output_dir, '%s_%d_sqlite.db' % (output_prefix, htmid))
        with sqlite3.connect(db_name, isolation_level='EXCLUSIVE') as conn:
            creation_cmd = '''CREATE TABLE alert_data
                           (uniqueId int, obshistId int, xPix float, yPix float,
                            chipNum int, dflux float, snr float, ra float, dec float)'''

            cursor = conn.cursor()
            cursor.execute(creation_cmd)
            conn.commit()

            creation_cmd = '''CREATE TABLE metadata
                           (obshistId int, TAI float, band int)'''
            cursor.execute(creation_cmd)
            conn.commit()

            for obs_dex in obs_valid_dex:
                obs = self._obs_list[obs_dex]
                cmd = '''INSERT INTO metadata
                      VALUES(%d, %.5f, %d)''' % (obs.OpsimMetaData['obsHistID'],
                      obs.mjd.TAI, mag_name_to_int[obs.bandpass])

                cursor.execute(cmd)
            conn.commit()

            creation_cmd = '''CREATE TABLE quiescent_flux
                          (uniqueId int, band int, flux float, snr float)'''

            cursor.execute(creation_cmd)
            conn.commit()

            creation_cmd = '''CREATE TABLE baseline_astrometry
                           (uniqueId int, ra real, dec real, pmRA real,
                            pmDec real, parallax real, TAI real)'''

            cursor.execute(creation_cmd)
            conn.commit()

            for chunk in data_iter:
                n_raw_obj = len(chunk)
                i_chunk += 1

                if chunk_cutoff>0 and i_chunk>=chunk_cutoff:
                    break

                n_time_last = 0
                # filter the chunk so that we are only considering sources that are in
                # the trixel being considered
                reduced_htmid = chunk['htmid'] >> n_bits_off

                valid_htmid = np.where(reduced_htmid == htmid)
                if len(valid_htmid[0]) == 0:
                    continue
                n_htmid_trim = n_raw_obj-len(valid_htmid[0])
                chunk = chunk[valid_htmid]
                n_obj += len(valid_htmid[0])

                (chip_name_dict,
                 dmag_arr,
                 dmag_arr_transpose,
                 time_arr) = self.filter_on_photometry_then_chip_name(chunk, column_query,
                                                                      obs_valid_dex,
                                                                      expmjd_list,
                                                                      photometry_catalog,
                                                                      dmag_cutoff)

                q_f_dict = {}
                q_m_dict = {}
                q_snr_dict = {}

                q_m_dict[0] = photometry_catalog.column_by_name('quiescent_lsst_u')
                q_m_dict[1] = photometry_catalog.column_by_name('quiescent_lsst_g')
                q_m_dict[2] = photometry_catalog.column_by_name('quiescent_lsst_r')
                q_m_dict[3] = photometry_catalog.column_by_name('quiescent_lsst_i')
                q_m_dict[4] = photometry_catalog.column_by_name('quiescent_lsst_z')
                q_m_dict[5] = photometry_catalog.column_by_name('quiescent_lsst_y')

                q_f_dict[0] = dummy_sed.fluxFromMag(q_m_dict[0])
                q_f_dict[1] = dummy_sed.fluxFromMag(q_m_dict[1])
                q_f_dict[2] = dummy_sed.fluxFromMag(q_m_dict[2])
                q_f_dict[3] = dummy_sed.fluxFromMag(q_m_dict[3])
                q_f_dict[4] = dummy_sed.fluxFromMag(q_m_dict[4])
                q_f_dict[5] = dummy_sed.fluxFromMag(q_m_dict[5])

                q_pmra = 1000.0*arcsecFromRadians(photometry_catalog.column_by_name('properMotionRa'))
                q_pmdec = 1000.0*arcsecFromRadians(photometry_catalog.column_by_name('properMotionDec'))
                q_parallax = 1000.0*arcsecFromRadians(photometry_catalog.column_by_name('parallax'))
                q_ra = np.degrees(photometry_catalog.column_by_name('raICRS'))
                q_dec = np.degrees(photometry_catalog.column_by_name('decICRS'))
                q_tai = photometry_catalog.obs_metadata.mjd.TAI

                q_snr_dict = {}
                for i_filter in range(6):

                    snr_template, local_gamma = calcSNR_m5(q_m_dict[i_filter],
                                                           self.bp_dict[mag_names[i_filter]],
                                                           obs_mag_cutoff[i_filter],
                                                           photParams, gamma=gamma_template[i_filter])
                    q_snr_dict[i_filter] = snr_template
                    gamma_template[i_filter] = local_gamma

                unq = photometry_catalog.column_by_name('uniqueId')

                try:
                    assert dmag_arr_transpose.shape == (len(chunk), len(mag_names), len(expmjd_list))
                except AssertionError:
                    print('dmag_arr_transpose_shape %s' % str(dmag_arr_transpose.shape))
                    print('should be (%d, %d, %d)' % (len(chunk), len(mag_names), len(expmjd_list)))
                    raise

                # only include those sources for which np.abs(delta_mag) >= dmag_cutoff
                # at some point in their history (note that delta_mag is defined with
                # respect to the quiescent magnitude)
                #
                # also demand that the magnitude at some point is less than obs_mag_cutoff

                photometrically_valid_obj = []
                for i_obj in range(len(chunk)):
                    keep_it = False
                    valid_times = np.where(time_arr[i_obj]>0)
                    if len(valid_times[0]) == 0:
                        continue
                    for i_filter in range(len(mag_names)):
                        if np.abs(dmag_arr_transpose[i_obj][i_filter][valid_times]).max()>dmag_cutoff:
                            dmag_min = dmag_arr_transpose[i_obj][i_filter][valid_times].min()
                            if q_m_dict[i_filter][i_obj] + dmag_min <= obs_mag_cutoff[i_filter]:
                                keep_it = True
                                break
                    if keep_it:
                        photometrically_valid_obj.append(i_obj)
                photometrically_valid_obj = np.array(photometrically_valid_obj)

                del dmag_arr_transpose
                gc.collect()

                if np.abs(dmag_arr).max() < dmag_cutoff:
                    continue

                completely_valid = np.zeros(len(chunk), dtype=int)

                ############################
                # Process and output sources
                #
                t_before_out = time.time()
                for i_obs, obs_dex in enumerate(obs_valid_dex):
                    obs = self._obs_list[obs_dex]
                    obshistid = obs.OpsimMetaData['obsHistID']

                    obs_mag = obs.bandpass
                    actual_i_mag = mag_name_to_int[obs_mag]
                    assert mag_names[actual_i_mag] == obs_mag

                    # only include those sources which fall on a detector for this pointing
                    valid_chip_name, valid_xpup, valid_ypup, chip_valid_obj = chip_name_dict[i_obs]

                    actually_valid_obj = np.intersect1d(photometrically_valid_obj, chip_valid_obj)
                    if len(actually_valid_obj) == 0:
                        continue

                    try:
                        completely_valid[actually_valid_obj] += 1
                    except:
                        print('failed')
                        print(actually_valid_obj)
                        print(completely_valid)
                        raise

                    valid_sources = chunk[actually_valid_obj]
                    local_column_cache = {}
                    local_column_cache['deltaMagAvro'] = OrderedDict([('delta_%smag' % mag_names[i_mag],
                                                                      dmag_arr[i_obs][i_mag][actually_valid_obj])
                                                                      for i_mag in range(len(mag_names))])

                    local_column_cache['chipName'] = valid_chip_name[actually_valid_obj]
                    local_column_cache['pupilFromSky'] = OrderedDict([('x_pupil', valid_xpup[actually_valid_obj]),
                                                                      ('y_pupil', valid_ypup[actually_valid_obj])])

                    i_star = 0
                    cat = cat_list[i_obs]
                    i_valid_chunk = 0
                    for valid_chunk, chunk_map in cat.iter_catalog_chunks(query_cache=[valid_sources], column_cache=local_column_cache):
                        i_valid_chunk += 1
                        assert i_valid_chunk == 1
                        n_time_last += len(valid_chunk[0])
                        length_of_chunk = len(valid_chunk[chunk_map['uniqueId']])
                        cache_tag = '%d_%d' % (obshistid, i_chunk)
                        output_data_cache[cache_tag] = {}

                        for col_name in ('uniqueId', 'raICRS', 'decICRS', 'flux', 'dflux', 'SNR',
                                         'chipNum', 'xPix', 'yPix'):

                            output_data_cache[cache_tag][col_name] = valid_chunk[chunk_map[col_name]]

                        n_rows_cached += length_of_chunk

                completely_valid = np.where(completely_valid>0)
                for i_filter in range(6):
                    values = ((int(unq[completely_valid][i_q]),
                               i_filter,
                               q_f_dict[i_filter][completely_valid][i_q],
                               q_snr_dict[i_filter][completely_valid][i_q])
                              for i_q in range(len(completely_valid[0])))
                    cursor.executemany('INSERT INTO quiescent_flux VALUES (?,?,?,?)', values)
                    conn.commit()

                values = ((int(unq[completely_valid][i_q]),
                           q_ra[completely_valid][i_q],
                           q_dec[completely_valid][i_q],
                           q_pmra[completely_valid][i_q],
                           q_pmdec[completely_valid][i_q],
                           q_parallax[completely_valid][i_q],
                           q_tai)
                          for i_q in range(len(completely_valid[0])))

                cursor.executemany('INSERT INTO baseline_astrometry VALUES (?,?,?,?,?,?,?)', values)

                if n_rows_cached >= write_every:
                    self.acquire_lock()
                    with open(log_file_name,'a') as out_file:
                        out_file.write('%d is writing \n' % os.getpid())

                        print('%d is writing' % os.getpid())

                    self.release_lock()

                    n_rows += self.output_alert_data(conn, output_data_cache, log_file_name)
                    output_data_cache = {}
                    n_rows_cached = 0

                    if n_rows>0:
                        self.acquire_lock()
                        with open(log_file_name,'a') as out_file:
                            elapsed = (time.time()-t_before_obj)/3600.0
                            elapsed_per = elapsed/n_rows
                            rows_per_chunk = float(n_rows)/float(i_chunk)
                            total_projection = 1000.0*rows_per_chunk*elapsed_per
                            out_file.write('\n    %d n_obj %d %d trimmed %d\n' %
                                           (this_pid, n_obj, n_actual_obj, n_htmid_trim))
                            out_file.write('    elapsed %.2e hrs per row %.2e total %2e\n' %
                                            (elapsed, elapsed_per, total_projection))
                            out_file.write('    n_time_last %d; rows %d\n' % (n_time_last,n_rows))

                            out_file.write('%d is done writing\n' % os.getpid())

                            print('\n    %d n_obj %d %d trimmed %d' %
                                           (this_pid, n_obj, n_actual_obj, n_htmid_trim))
                            print('    elapsed %.2e hrs per row %.2e total %2e' %
                                            (elapsed, elapsed_per, total_projection))
                            print('    n_time_last %d; rows %d\n' % (n_time_last,n_rows))
                            print('%d is done writing' % os.getpid())


                        self.release_lock()

            if len(output_data_cache)>0:
                n_rows += self.output_alert_data(conn, output_data_cache, log_file_name)
                output_data_cache = {}

            print('htmid %d that took %.2e hours; n_obj %d n_rows %d' %
                 (htmid, (time.time()-t_start)/3600.0, n_obj, n_rows))

            self.acquire_lock()
            print("INDEXING %d" % htmid)
            self.release_lock()

            cursor.execute('CREATE INDEX unq_obs ON alert_data (uniqueId, obshistId)')
            cursor.execute('CREATE INDEX unq_flux ON quiescent_flux (uniqueId, band)')
            cursor.execute('CREATE INDEX obs ON metadata (obshistid)')
            cursor.execute('CREATE INDEX unq_ast ON baseline_astrometry (uniqueId)')
            conn.commit()

            self.acquire_lock()
            with open(log_file_name, 'a') as out_file:
                out_file.write('done with htmid %d -- %e %d\n' %
                              (htmid,(time.time()-t_start)/3600.0,n_obj))
            self.release_lock()

        return n_rows
