import numpy as np
import re
import h5py
import multiprocessing as mproc
from collections import OrderedDict
import time
from lsst.sims.utils import findHtmid, trixelFromHtmid
from lsst.sims.utils import angularSeparation, ObservationMetaData
from lsst.sims.catUtils.utils import _baseLightCurveCatalog
from lsst.sims.utils import _pupilCoordsFromRaDec
from lsst.sims.coordUtils import chipNameFromPupilCoordsLSST
from lsst.sims.coordUtils import pixelCoordsFromPupilCoords
from lsst.sims.coordUtils import lsst_camera

from lsst.sims.catalogs.decorators import compound, cached
from lsst.sims.photUtils import BandpassDict, Sed, calcSNR_m5
from lsst.sims.photUtils import PhotometricParameters
from lsst.sims.catUtils.mixins import VariabilityStars, AstrometryStars
from lsst.sims.catUtils.mixins import CameraCoordsLSST, PhotometryBase
from lsst.sims.catUtils.mixins import ParametrizedLightCurveMixin
from lsst.sims.catUtils.mixins import create_variability_cache


__all__ = ["AlertDataGenerator",
           "AlertStellarVariabilityCatalog",
           "_baseAlertCatalog"]


class _baseAlertCatalog(_baseLightCurveCatalog):

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


class AlertStellarVariabilityCatalog(VariabilityStars, AstrometryStars, PhotometryBase,
                                     CameraCoordsLSST, _baseAlertCatalog):
    column_outputs = ['uniqueId', 'raICRS', 'decICRS',
                      'flux', 'SNR', 'dflux',
                      'chipNum', 'xPix', 'yPix']

    default_formats = {'f':'%.4g'}

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


    @compound('quiescent_lsst_u', 'quiescent_lsst_g', 'quiescent_lsst_r',
              'quiescent_lsst_i', 'quiescent_lsst_z', 'quiescent_lsst_y')
    def get_quiescent_lsst_magnitudes(self):
        return np.array([self.column_by_name('umag'), self.column_by_name('gmag'),
                         self.column_by_name('rmag'), self.column_by_name('imag'),
                         self.column_by_name('zmag'), self.column_by_name('ymag')])

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
    def get_avroPhotometry(self):
        mag = self.column_by_name('lsst_%s' % self.obs_metadata.bandpass)
        quiescent_mag = self.column_by_name('%smag' % self.obs_metadata.bandpass)
        dmag = mag - quiescent_mag

        return np.array([mag, dmag, quiescent_mag])

    @compound('flux', 'dflux', 'SNR')
    def get_avroFlux(self):
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
        if not hasattr(self, '_gamma_template'):
            self._gamma_template = None

        # taken from Table 2 of overview paper
        # (might not be appropriate; is just a placeholder)
        template_m5 = {'u':23.9, 'g':25.0, 'r':24.7, 'i':24.0, 'z':23.3, 'y':22.1}

        quiescent_flux = self._dummy_sed.fluxFromMag(quiescent_mag)
        flux = self._dummy_sed.fluxFromMag(mag)
        dflux = flux - quiescent_flux

        snr_tot, gamma = calcSNR_m5(mag, self.lsstBandpassDict[self.obs_metadata.bandpass],
                                    self.obs_metadata.m5[self.obs_metadata.bandpass],
                                    self.photParams, gamma=self._gamma)

        if self._gamma is None:
            self._gamma = gamma

        snr_template, gamma_template = calcSNR_m5(quiescent_mag,
                                                  self.lsstBandpassDict[self.obs_metadata.bandpass],
                                                  template_m5[self.obs_metadata.bandpass],
                                                  self.photParams, gamma=self._gamma_template)

        if self._gamma_template is None:
            self._gamma_template = gamma_template

        sigma = np.sqrt((flux/snr_tot)**2 + (quiescent_flux/snr_template)**2)
        snr = dflux/sigma

        return np.array([flux, dflux, snr])


def _find_chipNames_parallel(ra, dec, pm_ra=None, pm_dec=None, parallax=None,
                             v_rad=None, obs_metadata_list=None, i_obs_list=None, out_dict=None):

    for i_obs, obs in zip(i_obs_list, obs_metadata_list):
        xPup_list, yPup_list = _pupilCoordsFromRaDec(ra, dec, pm_ra=pm_ra,
                                                     pm_dec=pm_dec, parallax=parallax,
                                                     v_rad=v_rad, obs_metadata=obs)

        chip_name_list = chipNameFromPupilCoordsLSST(xPup_list, yPup_list)

        chip_int_arr = -1*np.ones(len(chip_name_list), dtype=int)
        for i_chip, name in enumerate(chip_name_list):
            if name is not None:
                chip_int_arr[i_chip] = 1
        valid_obj = np.where(chip_int_arr>0)

        out_dict[i_obs] = (chip_name_list[valid_obj],
                           xPup_list[valid_obj], yPup_list[valid_obj],
                           valid_obj)


class AlertDataGenerator(object):

    def __init__(self, n_proc_max=4, output_prefix='test_hdf5',
                 dmag_cutoff=0.005,
                 photometry_class=AlertStellarVariabilityCatalog,
                 testing=False):

        self._photometry_class = photometry_class
        self._output_prefix = output_prefix
        self._dmag_cutoff = dmag_cutoff
        self._n_proc_max = n_proc_max
        self._variability_cache = create_variability_cache()
        if not testing:
            plm = ParametrizedLightCurveMixin()
            plm.load_parametrized_light_curves(variability_cache = self._variability_cache)
        self.bp_dict = BandpassDict.loadTotalBandpassesFromFiles()
        self.chunk_size = 10000
        self._desired_columns = []
        self._desired_columns.append('simobjid')
        self._desired_columns.append('variabilityParameters')
        self._desired_columns.append('varParamStr')
        self._desired_columns.append('raJ2000')
        self._desired_columns.append('decJ2000')
        self._desired_columns.append('properMotionRa')
        self._desired_columns.append('properMotionDec')
        self._desired_columns.append('parallax')
        self._desired_columns.append('radialVelocity')
        self._desired_columns.append('umag')
        self._desired_columns.append('gmag')
        self._desired_columns.append('rmag')
        self._desired_columns.append('imag')
        self._desired_columns.append('zmag')
        self._desired_columns.append('ymag')
        self._desired_columns.append('ebv')
        self._desired_columns.append('redshift')

    def subdivide_obs(self, obs_list):
        obs_list = np.array(obs_list)
        htmid_level = 7
        htmid_list = []
        for obs in obs_list:
            htmid = findHtmid(obs.pointingRA, obs.pointingDec, htmid_level)
            htmid_list.append(htmid)
        htmid_list = np.array(htmid_list)
        self._unq_htmid_list = np.unique(htmid_list)

        self._htmid_dict = {}
        for htmid in self._unq_htmid_list:
            valid_dexes = np.where(htmid_list == htmid)
            self._htmid_dict[htmid] = obs_list[valid_dexes]

        print('%d obs; %d unique_htmid' % (len(obs_list), len(self._unq_htmid_list)))

    @property
    def htmid_list(self):
        """
        A list of the unique htmid's corresponding to the fields
        of view that need to be queried to generate the alert data
        """
        return self._unq_htmid_list


    def output_to_hdf5(self, hdf5_file, data_cache):
        """
        Cache will be keyed first on the obsHistID, then all of the columns
        """
        self._output_ct += 1
        for obsHistID in data_cache.keys():
            if obsHistID not in self._obs_hist_to_ct_map:
                self._obs_hist_to_ct_map[obsHistID] = []

            self._obs_hist_to_ct_map[obsHistID].append(self._output_ct)

            for unique_id in data_cache[obsHistID]['uniqueId']:
                if unique_id not in self._unique_id_set:
                    self._unique_id_set.add(unique_id)
                    self._unique_id_obshistid_map[unique_id] = []
                    self._unique_id_chunk_map[unique_id] = []

                self._unique_id_obshistid_map[unique_id].append(obsHistID)
                self._unique_id_chunk_map[unique_id].append(self._output_ct)

            for col_name in data_cache[obsHistID].keys():
                data_tag = '%d_%d_%s' % (obsHistID, self._output_ct, col_name)
                hdf5_file.create_dataset(data_tag, data=np.array(data_cache[obsHistID][col_name]))

        hdf5_file.flush()

    def alert_data_from_htmid(self, htmid, dbobj, radius=1.75):

        t_start = time.time()

        self._output_ct = -1
        self._obs_hist_to_ct_map = {}
        self._unique_id_set = set()
        self._unique_id_obshistid_map = {}
        self._unique_id_chunk_map = {}
        out_file = h5py.File('%s_%d.hdf5' % (self._output_prefix, htmid), 'w')

        # a dummy call to make sure that the initialization
        # is done before we attempt to parallelize calls
        # to chipNameFromRaDecLSST
        dummy_name = chipNameFromPupilCoordsLSST(0.0, 0.0)

        mag_names = ('u', 'g', 'r', 'i', 'z', 'y')
        obs_valid = self._htmid_dict[htmid]
        print('n valid obs %d' % len(obs_valid))
        center_trixel = trixelFromHtmid(htmid)
        center_ra, center_dec = center_trixel.get_center()

        ra_list = []
        dec_list = []
        cat_list = []
        expmjd_list = []
        obshistid_list = []
        band_list = []
        mag_name_to_int = {'u':0, 'g':1, 'r':2, 'i':3, 'z':4, 'y':5}
        for obs in obs_valid:
            ra_list.append(obs.pointingRA)
            dec_list.append(obs.pointingDec)
            cat = self._photometry_class(dbobj, obs_metadata=obs)
            cat.lsstBandpassDict =  self.bp_dict
            cat_list.append(cat)
            expmjd_list.append(obs.mjd.TAI)
            obshistid_list.append(obs.OpsimMetaData['obsHistID'])
            band_list.append(mag_name_to_int[obs.bandpass])

        expmjd_list = np.array(expmjd_list)
        obshistid_list = np.array(obshistid_list)
        band_list = np.array(band_list)
        cat_list = np.array(cat_list)
        ra_list = np.array(ra_list)
        dec_list = np.array(dec_list)
        sorted_dex = np.argsort(expmjd_list)

        expmjd_list = expmjd_list[sorted_dex]
        ra_list = ra_list[sorted_dex]
        dec_list = dec_list[sorted_dex]
        cat_list = cat_list[sorted_dex]
        obs_valid = obs_valid[sorted_dex]
        obshistid_list = obshistid_list[sorted_dex]
        band_list = band_list[sorted_dex]

        out_file.create_dataset('obshistID', data=obshistid_list)
        out_file.create_dataset('TAI', data=expmjd_list)
        out_file.create_dataset('bandpass', data=band_list)
        out_file.flush()

        print('built list')

        dist_list = angularSeparation(center_ra, center_dec, ra_list, dec_list)
        radius += dist_list.max()
        center_obs = ObservationMetaData(pointingRA=center_ra,
                                         pointingDec=center_dec,
                                         boundType='circle',
                                         boundLength=radius)

        print('radius %e' % radius)

        available_columns = list(dbobj.columnMap.keys())
        column_query = []
        for col in self._desired_columns:
            if col in available_columns:
                column_query.append(col)

        data_iter = dbobj.query_columns(colnames=column_query,
                                        obs_metadata=center_obs,
                                        chunk_size=self.chunk_size)


        photometry_catalog = self._photometry_class(dbobj, obs_valid[0],
                                                    column_outputs=['lsst_u',
                                                                    'lsst_g',
                                                                    'lsst_r',
                                                                    'lsst_i',
                                                                    'lsst_z',
                                                                    'lsst_y'])

        print('chunking')
        i_chunk = 0
        t_chipName = 0.0

        n_proc_possible = int(np.ceil(len(obs_valid)/5.0))
        n_proc_chipName = min(n_proc_possible, self._n_proc_max)

        output_data_cache = {}
        ct_to_write = 0

        for chunk in data_iter:
            i_chunk += 1
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
            if n_proc_chipName == 1:
                chip_name_dict = {}
            else:
                mgr = mproc.Manager()
                chip_name_dict = mgr.dict()
                iobs_sub_list = []
                obs_sub_list = []
                for i_obs in range(n_proc_chipName):
                    iobs_sub_list.append([])
                    obs_sub_list.append([])
                sub_list_ct = 0

            for i_obs, obs in enumerate(obs_valid):
                if n_proc_chipName == 1:
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
                    chip_name_dict[i_obs] = (chip_name_list[valid_obj],
                                             xPup_list[valid_obj],
                                             yPup_list[valid_obj],
                                             valid_obj)

                else:
                    iobs_sub_list[sub_list_ct].append(i_obs)
                    obs_sub_list[sub_list_ct].append(obs)
                    sub_list_ct += 1
                    if sub_list_ct >= n_proc_chipName:
                        sub_list_ct = 0

            if n_proc_chipName>1:
                process_list = []
                for sub_list_ct in range(len(iobs_sub_list)):
                    p = mproc.Process(target=_find_chipNames_parallel,
                                      args=(chunk['raJ2000'], chunk['decJ2000']),
                                      kwargs={'pm_ra': pmra,
                                              'pm_dec': pmdec,
                                              'parallax': px,
                                              'v_rad': vrad,
                                              'obs_metadata_list': obs_sub_list[sub_list_ct],
                                              'i_obs_list': iobs_sub_list[sub_list_ct],
                                              'out_dict': chip_name_dict})
                    p.start()
                    process_list.append(p)

                for p in process_list:
                    p.join()

                assert len(chip_name_dict) == len(obs_valid)

            ######################################################
            # Calculate the delta_magnitude for all of the sources
            #
            t_before_phot = time.time()

            # only calculate photometry for objects that actually land
            # on LSST detectors

            valid_photometry = -1*np.ones(len(chunk))

            t_before_filter = time.time()
            for i_obs in range(len(obs_valid)):
                name_list, xpup_list, ypup_list, valid_obj = chip_name_dict[i_obs]
                valid_photometry[valid_obj] += 2
            invalid_dex = np.where(valid_photometry<0)
            chunk['varParamStr'][invalid_dex] = 'None'

            photometry_catalog._set_current_chunk(chunk)
            dmag_arr = photometry_catalog.applyVariability(chunk['varParamStr'],
                                                           variability_cache=self._variability_cache,
                                                           expmjd=expmjd_list,).transpose((2,0,1))

            if np.abs(dmag_arr).max() < self._dmag_cutoff:
                continue

            ############################
            # Process and output sources
            #
            t_before_out = time.time()
            for i_obs, obs in enumerate(obs_valid):
                obshistid = obs.OpsimMetaData['obsHistID']

                obs_mag = obs.bandpass
                actual_i_mag = mag_name_to_int[obs_mag]
                assert mag_names[actual_i_mag] == obs_mag

                # only include those sources which fall on a detector for this pointing
                valid_chip_name, valid_xpup, valid_ypup, valid_obj = chip_name_dict[i_obs]

                actually_valid_sources = np.where(np.abs(dmag_arr[i_obs][actual_i_mag][valid_obj]) >= self._dmag_cutoff)
                if len(actually_valid_sources[0]) == 0:
                    continue

                # only include those sources for which np.abs(delta_mag) >= self._dmag_cutoff
                # this is technically only selecting sources that differ from the quiescent
                # magnitude by at least self._dmag_cutoff.  If a source changes from quiescent_mag+dmag
                # to quiescent_mag, it will not make the cut

                valid_sources = chunk[valid_obj][actually_valid_sources]
                local_column_cache = {}
                local_column_cache['deltaMagAvro'] = OrderedDict([('delta_%smag' % mag_names[i_mag],
                                                                  dmag_arr[i_obs][i_mag][valid_obj][actually_valid_sources])
                                                                  for i_mag in range(len(mag_names))])

                local_column_cache['chipName'] = valid_chip_name[actually_valid_sources]
                local_column_cache['pupilFromSky'] = OrderedDict([('x_pupil', valid_xpup[actually_valid_sources]),
                                                                  ('y_pupil', valid_ypup[actually_valid_sources])])

                i_star = 0
                cat = cat_list[i_obs]
                for valid_chunk, chunk_map in cat.iter_catalog_chunks(query_cache=[valid_sources], column_cache=local_column_cache):

                    if obshistid not in output_data_cache:
                        output_data_cache[obshistid] = {}


                    data_tag = '%d_%d' % (obs.OpsimMetaData['obsHistID'], i_chunk)

                    for col_name in ('uniqueId', 'raICRS', 'decICRS', 'flux', 'dflux', 'SNR',
                                     'chipNum', 'xPix', 'yPix'):
                        if col_name not in output_data_cache[obshistid]:
                            output_data_cache[obshistid][col_name] = list(valid_chunk[chunk_map[col_name]])
                        else:
                            output_data_cache[obshistid][col_name] += list(valid_chunk[chunk_map[col_name]])

                    ct_to_write += len(valid_chunk[chunk_map['uniqueId']])
                    # print('ct_to_write %d' % ct_to_write)
                    if ct_to_write >= 10000:
                        self.output_to_hdf5(out_file, output_data_cache)
                        ct_to_write = 0
                        output_data_cache = {}

                    #print star_obj
                #if i_chunk > 10:
                #    exit()

        if len(output_data_cache)>0:
            self.output_to_hdf5(out_file, output_data_cache)

        for obshistid in self._obs_hist_to_ct_map:
            tag = '%d_map' % obshistid
            out_file.create_dataset(tag, data=np.array(self._obs_hist_to_ct_map[obshistid]))

        out_file.create_dataset('uniqueId_list', data=np.array(self._unique_id_set))
        for unique_id in self._unique_id_set:
            tag = '%d_obshistid_map' % unique_id
            outfile.create_dataset(tag, data=np.array(self._unique_id_obshistid_map[unique_id]))
            tag = '%d_chunk_map' % unique_id
            outfile.create_dataset(tag, data=np.array(self._unique_id_chunk_map[unique_id]))

        out_file.close()
        print('that took %.2e hours per obs for %d obs' %
              ((time.time()-t_start)/(3600.0*len(obs_valid)), len(obs_valid)))

        return len(obs_valid)