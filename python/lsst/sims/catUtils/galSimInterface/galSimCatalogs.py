"""
The catalog classes in this file use the InstanceCatalog infrastructure to construct
FITS images for each detector-filter combination on a simulated camera.  This is done by
instantiating the class GalSimInterpreter.  This GalSimInterpreter is the class which
actually generates the FITS images.  As the GalSim InstanceCatalogs are iterated over,
each object in the catalog is passed to to the GalSimInterpeter, which adds the object
to the appropriate FITS images.  The user can then write the images to disk by calling
the write_images method in the GalSim InstanceCatalog.

Objects are passed to the GalSimInterpreter by the get_fitsFiles getter function, which
adds a column to the InstanceCatalog indicating which detectors' FITS files contain each image.

Note: because each GalSim InstanceCatalog has its own GalSimInterpreter, it means
that each GalSimInterpreter will only draw FITS images containing one type of object
(whatever type of object is contained in the GalSim InstanceCatalog).  If the user
wishes to generate FITS images containing multiple types of object, the method
copyGalSimInterpreter allows the user to pass the GalSimInterpreter from one
GalSim InstanceCatalog to another (so, the user could create a GalSim Instance
Catalog of stars, generate that InstanceCatalog, then create a GalSim InstanceCatalog
of galaxies, pass the GalSimInterpreter from the star catalog to this new catalog,
and thus create FITS images that contain both stars and galaxies).
"""

import numpy
import os
import eups
import copy
from lsst.sims.utils import radiansToArcsec
from lsst.sims.catalogs.measures.instance import InstanceCatalog, cached, is_null
from lsst.sims.coordUtils import CameraCoords, AstrometryGalaxies, AstrometryStars
from lsst.sims.catUtils.galSimInterface import GalSimInterpreter, GalSimDetector
from lsst.sims.photUtils import EBVmixin, Sed, Bandpass, PhotometryHardware, PhotometricDefaults
import lsst.afw.cameraGeom.testUtils as camTestUtils
import lsst.afw.geom as afwGeom
from lsst.afw.cameraGeom import PUPIL, PIXELS, FOCAL_PLANE

__all__ = ["GalSimGalaxies", "GalSimAgn", "GalSimStars"]

class GalSimBase(InstanceCatalog, CameraCoords, PhotometryHardware):
    """
    The catalog classes in this file use the InstanceCatalog infrastructure to construct
    FITS images for each detector-filter combination on a simulated camera.  This is done by
    instantiating the class GalSimInterpreter.  GalSimInterpreter is the class which
    actually generates the FITS images.  As the GalSim InstanceCatalogs are iterated over,
    each object in the catalog is passed to to the GalSimInterpeter, which adds the object
    to the appropriate FITS images.  The user can then write the images to disk by calling
    the write_images method in the GalSim InstanceCatalog.

    Objects are passed to the GalSimInterpreter by the get_fitsFiles getter function, which
    adds a column to the InstanceCatalog indicating which detectors' FITS files contain each image.

    Note: because each GalSim InstanceCatalog has its own GalSimInterpreter, it means
    that each GalSimInterpreter will only draw FITS images containing one type of object
    (whatever type of object is contained in the GalSim InstanceCatalog).  If the user
    wishes to generate FITS images containing multiple types of object, the method
    copyGalSimInterpreter allows the user to pass the GalSimInterpreter from one
    GalSim InstanceCatalog to another (so, the user could create a GalSim Instance
    Catalog of stars, generate that InstanceCatalog, then create a GalSim InstanceCatalog
    of galaxies, pass the GalSimInterpreter from the star catalog to this new catalog,
    and thus create FITS images that contain both stars and galaxies; see galSimCompoundGenerator.py
    in the examples/ directory of sims_catUtils for an example).

    This class (GalSimBase) is the base class for all GalSim InstanceCatalogs.  Daughter
    classes of this class need to behave like ordinary InstanceCatalog daughter classes
    with the following exceptions:

    1) If they re-define column_outputs, they must be certain to include the column
    'fitsFiles', as the getter for this column (defined in this class) calls all of the
    GalSim image generation infrastructure

    2) Daughter classes of this class must define a member variable galsim_type that is either
    'sersic' or 'pointSource'.  This variable tells the GalSimInterpreter how to draw the
    object (to allow a different kind of image profile, define a new method in the GalSimInterpreter
    class similar to drawPoinSource and drawSersic)

    3) The variables bandpass_names (a list of the form ['u', 'g', 'r', 'i', 'z', 'y']),
    bandpass_directory, and bandpass_root should be defined to tell the GalSim InstanceCatalog
    where to find the files defining the bandpasses to be used for these FITS files.
    The GalSim InstanceCatalog will look for bandpass files in files with the names

    for bpn in bandpass_names:
        name = self.bandpass_directory+'/'+self.bandpass_root+'_'+bpn+'.dat'

    4) Telescope parameters such as exposure time, area, and gain are controled by the
    GalSim InstanceCatalog member variables exposure_time (in s), effective_area (in cm^2),
    and gain (in photons per ADU)

    Daughter classes of GalSimBase will generate both FITS images for all of the detectors/filters
    in their corresponding cameras and InstanceCatalogs listing all of the objects
    contained in those images.  The catalog is written using the normal write_catalog()
    method provided for all InstanceClasses.  The FITS files are drawn using the write_images()
    method that is unique to GalSim InstanceCatalogs.  The FITS file will be named something like:

    DetectorName_FilterName.fits

    (a typical LSST fits file might be R_0_0_S_1_0_y.fits)

    Note: If you call write_images() before iterating over the catalog (either by calling
    write_catalog() or using the iterator returned by InstanceCatalog.iter_catalog()),
    you will get empty or incomplete FITS files.  Objects are only added to the GalSimInterpreter
    in the course of iterating over the InstanceCatalog.
    """

    #This is sort of a hack; it prevents findChipName in coordUtils from dying
    #if an object lands on multiple science chips.
    allow_multiple_chips = True

    #There is no point in writing things to the InstanceCatalog that do not have SEDs and/or
    #do not land on any detectors
    cannot_be_null = ['sedFilepath', 'fitsFiles']

    column_outputs = ['galSimType', 'uniqueId', 'chipName', 'x_pupil', 'y_pupil', 'sedFilepath',
                      'majorAxis', 'minorAxis', 'sindex', 'halfLightRadius',
                      'positionAngle','fitsFiles']

    transformations = {'x_pupil':radiansToArcsec,
                       'y_pupil':radiansToArcsec,
                       'halfLightRadius':radiansToArcsec}

    default_formats = {'S':'%s', 'f':'%.9g', 'i':'%i'}

    #This is used as the delimiter because the names of the detectors printed in the fitsFiles
    #column contain both ':' and ','
    delimiter = ';'

    bandpassNames = ['u', 'g', 'r', 'i', 'z', 'y']
    bandpassDir = os.path.join(eups.productDir('throughputs'), 'baseline')
    bandpassRoot = 'filter_'
    componentList = ['detector.dat', 'm1.dat', 'm2.dat', 'm3.dat',
                     'lens1.dat', 'lens2.dat', 'lens3.dat']
    skyBandpassName = 'atmos.dat'
    skySEDname = 'darksky.dat'

    #This member variable will define a PSF to convolve with the sources.
    #See the classes PSFbase and DoubleGaussianPSF in
    #galSimUtilities.py for more information
    PSF = None

    #This member variable can store a GalSim noise model instantiation
    #which will be applied to the FITS images by calling add_noise()
    noise_and_background = None

    #Consulting the file sed.py in GalSim/galsim/ it appears that GalSim expects
    #its SEDs to ultimately be in units of ergs/nm so that, when called, they can
    #be converted to photons/nm (see the function __call__() and the assignment of
    #self._rest_photons in the __init__() of galsim's sed.py file).  Thus, we need
    #to read in our SEDs, normalize them, and then multiply by the exposure time
    #and the effective area to get from ergs/s/cm^2/nm to ergs/nm.
    #
    #The gain parameter should convert between photons and ADU (so: it is the
    #traditional definition of "gain" -- electrons per ADU -- multiplied by the
    #quantum efficiency of the detector).  Because we fold the quantum efficiency
    #of the detector into our total_[u,g,r,i,z,y].dat bandpass files
    #(see the readme in the THROUGHPUTS_DIR/baseline/), we only need to multiply
    #by the electrons per ADU gain.
    #
    #These parameters can be set to different values by redefining them in daughter
    #classes of this class.
    #
    effective_area = PhotometricDefaults.effarea
    exposure_time = PhotometricDefaults.exptime
    gain = PhotometricDefaults.gain

    #This is just a place holder for the camera object associated with the InstanceCatalog.
    #If you want to assign a different camera, you can do so immediately after instantiating this class
    camera = camTestUtils.CameraWrapper().camera


    uniqueSeds = {} #a cache for un-normalized SED files, so that we do not waste time on I/O

    hasBeenInitialized = False

    galSimInterpreter = None #the GalSimInterpreter instantiation for this catalog
                             #This class is either passed in from another catalog using
                             #copyGalSimInterpreter, or initialized in the write_header method

    totalDrawings = 0
    totalObjects = 0

    def _initializeGalSimCatalog(self):
        """
        Initializes an empty list of objects that have already been drawn to FITS images.
        We do not want to accidentally draw an object twice.

        Also initializes the GalSimInterpreter by calling self._initializeGalSimInterpreter()

        Objects are stored based on their uniqueId values.
        """
        self.objectHasBeenDrawn = []
        self._initializeGalSimInterpreter()
        self.hasBeenInitialized = True

    def get_sedFilepath(self):
        """
        Maps the name of the SED as stored in the database to the file stored in
        sims_sed_library
        """
        #copied from the phoSim catalogs
        return numpy.array([self.specFileMap[k] if self.specFileMap.has_key(k) else None
                         for k in self.column_by_name('sedFilename')])

    def _calculateGalSimSeds(self):
        """
        Apply any physical corrections to the objects' SEDS (redshift them, apply dust, etc.).
        Return a list of Sed objects containing the SEDS
        """

        sedList = []
        actualSEDnames = self.column_by_name('sedFilepath')
        redshift = self.column_by_name('redshift')
        internalAv = self.column_by_name('internalAv')
        internalRv = self.column_by_name('internalRv')
        galacticAv = self.column_by_name('galacticAv')
        galacticRv = self.column_by_name('galacticRv')
        magNorm = self.column_by_name('magNorm')

        sedDir = os.getenv('SIMS_SED_LIBRARY_DIR')

        #for setting magNorm
        imsimband = Bandpass()
        imsimband.imsimBandpass()

        outputNames=[]

        for (sedName, zz, iAv, iRv, gAv, gRv, norm) in \
            zip(actualSEDnames, redshift, internalAv, internalRv, galacticAv, galacticRv, magNorm):

            if is_null(sedName):
                sedList.append(None)
            else:
                if sedName in self.uniqueSeds:
                    #we have already read in this file; no need to do it again
                    sed = Sed(wavelen=self.uniqueSeds[sedName].wavelen,
                              flambda=self.uniqueSeds[sedName].flambda,
                              fnu=self.uniqueSeds[sedName].fnu,
                              name=self.uniqueSeds[sedName].name)
                else:
                    #load the SED of the object
                    sed = Sed()
                    sedFile = os.path.join(sedDir, sedName)
                    sed.readSED_flambda(sedFile)

                    flambdaCopy = copy.deepcopy(sed.flambda)

                    #If the SED is zero inside of the bandpass, GalSim raises an error.
                    #This sets a minimum flux value of 1.0e-30 so that the SED is never technically
                    #zero inside of the bandpass.
                    sed.flambda = numpy.array([ff if ff>1.0e-30 else 1.0e-30 for ff in flambdaCopy])
                    sed.fnu = None

                    #copy the unnormalized file to uniqueSeds so we don't have to read it in again
                    sedCopy = Sed(wavelen=sed.wavelen, flambda=sed.flambda,
                                  fnu=sed.fnu, name=sed.name)
                    self.uniqueSeds[sedName] = sedCopy

                #normalize the SED
                fNorm = sed.calcFluxNorm(norm, imsimband)
                sed.multiplyFluxNorm(fNorm*self.exposure_time*self.effective_area)

                #apply dust extinction (internal)
                if iAv != 0.0 and iRv != 0.0:
                    a_int, b_int = sed.setupCCMab()
                    sed.addCCMDust(a_int, b_int, A_v=iAv, R_v=iRv)

                #13 November 2014
                #apply redshift; there is no need to apply the distance modulus from
                #sims/photUtils/CosmologyWrapper; I believe magNorm takes that into account
                #
                #also: no need to apply dimming for the same reason
                if zz != 0.0:
                    sed.redshiftSED(zz, dimming=False)

                #apply dust extinction (galactic)
                a_int, b_int = sed.setupCCMab()
                sed.addCCMDust(a_int, b_int, A_v=gAv, R_v=gRv)
                sedList.append(sed)

        return sedList


    def get_fitsFiles(self):
        """
        This getter returns a column listing the names of the detectors whose corresponding
        FITS files contain the object in question.  The detector names will be separated by a '//'

        This getter also passes objects to the GalSimInterpreter to actually draw the FITS
        images.
        """
        objectNames = self.column_by_name('uniqueId')
        xPupil = self.column_by_name('x_pupil')
        yPupil = self.column_by_name('y_pupil')
        halfLight = self.column_by_name('halfLightRadius')
        minorAxis = self.column_by_name('minorAxis')
        majorAxis = self.column_by_name('majorAxis')
        positionAngle = self.column_by_name('positionAngle')
        sindex = self.column_by_name('sindex')

        #correct the SEDs for redshift, dust, etc.  Return a list of Sed objects as defined in
        #sims_photUtils/../../Sed.py
        sedList = self._calculateGalSimSeds()

        if self.hasBeenInitialized is False:
            #This needs to be here in case, instead of writing the whole catalog with write_catalog(),
            #the user wishes to iterate through the catalog with InstanceCatalog.iter_catalog(),
            #which will not call write_header()
            self._initializeGalSimCatalog()

        output = []
        for (name, xp, yp, hlr, minor, major, pa, ss, sn) in \
            zip(objectNames, xPupil, yPupil, halfLight, minorAxis, majorAxis, positionAngle,
            sedList, sindex):

            if ss is None or name in self.objectHasBeenDrawn:
                #do not draw objects that have no SED or have already been drawn
                output.append(None)
                if name in self.objectHasBeenDrawn:
                    #15 December 2014
                    #This should probably be an error.  However, something is wrong with
                    #the SQL on fatboy such that it does return the same objects more than
                    #once (at least in the case of stars).  Yusra is currently working to fix
                    #the problem.  Until then, this will just warn you that the same object
                    #appears twice in your catalog and will refrain from drawing it the second
                    #time.
                    print 'Trying to draw %s more than once ' % str(name)

            else:

                self.objectHasBeenDrawn.append(name)

                #actually draw the object
                detectorsString = self.galSimInterpreter.drawObject(galSimType=self.galsim_type,
                                                  sindex=sn, minorAxis=minor,
                                                  majorAxis=major, positionAngle=pa, halfLightRadius=hlr,
                                                  xPupil=xp, yPupil=yp, sed=ss)

                output.append(detectorsString)

        return numpy.array(output)

    def copyGalSimInterpreter(self, otherCatalog):
        """
        Copy the camera, GalSimInterpreter, from another GalSim InstanceCatalog
        so that multiple types of object (stars, AGN, galaxy bulges, galaxy disks, etc.)
        can be drawn on the same FITS files.

        @param [in] otherCatalog is another GalSim InstanceCatalog that already has
        an initialized GalSimInterpreter

        See galSimCompoundGenerator.py in the examples/ directory of sims_catUtils for
        an example of how this is used.
        """
        self.camera = otherCatalog.camera
        self.galSimInterpreter = otherCatalog.galSimInterpreter

        #set the PSF to the current PSF; in this way, compound FITS files do not
        #have to have the same PSF for all types of objects (though I'm not sure
        #that is actually physical)
        self.galSimInterpreter.setPSF(self.PSF)

    def write_header(self, file_handle):
        """
        This method adds to the InstanceCatalog.write_header() method.
        It writes information about all of the detectors in the camera to the header of the
        catalog output file.

        For each detector it writes:

        detector name
        center coordinates in arc seconds
        xmin and xmax in arc seconds
        ymin and ymax in arc seconds
        plateScale (arc seconds per pixel)



        It will also call self._initializeGalSimCatalog() if need be.
        """

        if not self.hasBeenInitialized:
            self._initializeGalSimCatalog()

        for detector in self.galSimInterpreter.detectors:
            file_handle.write('#detector;%s;%f;%f;%f;%f;%f;%f;%f\n' %
                                 (detector.name, detector.xCenter, detector.yCenter, detector.xMin,
                                  detector.xMax, detector.yMin, detector.yMax, detector.plateScale))

        InstanceCatalog.write_header(self, file_handle)

    def _initializeGalSimInterpreter(self):
        """
        This method creates the GalSimInterpreter (if it is None)

        This method reads in all of the data about the camera and pass it into
        the GalSimInterpreter.

        This method calls _getBandpasses to construct the paths to
        the files containing the bandpass data.
        """

        if self.galSimInterpreter is None:

            #build a dict of m5 values keyed on bandpass names
            m5Dict = None
            if self.noise_and_background is not None:
                m5Dict = {}
                for m5Name in self.bandpassNames:
                    if self.obs_metadata.m5 is not None and m5Name in self.obs_metadata.m5:
                        m5Dict[m5Name] = self.obs_metadata.m5[m5Name]
                    elif m5Name in PhotometricDefaults.m5:
                        m5Dict[m5Name] = PhotometricDefaults.m5[m5Name]
                    else:
                        raise RuntimeError('Do not know how to calculate m5 for bandpass %s ' % m5Name)

            #This list will contain instantiations of the GalSimDetector class
            #(see galSimInterpreter.py), which stores detector information in a way
            #that the GalSimInterpreter will understand
            detectors = []

            for dd in self.camera:
                cs = dd.makeCameraSys(PUPIL)
                centerPupil = self.camera.transform(dd.getCenter(FOCAL_PLANE),cs).getPoint()
                centerPixel = dd.getCenter(PIXELS).getPoint()

                translationPixel = afwGeom.Point2D(centerPixel.getX()+1, centerPixel.getY()+1)
                translationPupil = self.camera.transform(
                                        dd.makeCameraPoint(translationPixel, PIXELS), cs).getPoint()

                plateScale = numpy.sqrt(numpy.power(translationPupil.getX()-centerPupil.getX(),2)+
                                        numpy.power(translationPupil.getY()-centerPupil.getY(),2))/numpy.sqrt(2.0)
                xmax = None
                xmin = None
                ymax = None
                ymin = None
                for corner in dd.getCorners(FOCAL_PLANE):
                    pt = self.camera.makeCameraPoint(corner, FOCAL_PLANE)
                    pp = self.camera.transform(pt, cs).getPoint()
                    if xmax is None or pp.getX() > xmax:
                        xmax = pp.getX()
                    if xmin is None or pp.getX() < xmin:
                        xmin = pp.getX()
                    if ymax is None or pp.getY() > ymax:
                        ymax = pp.getY()
                    if ymin is None or pp.getY() < ymin:
                        ymin = pp.getY()

                xCenter = 3600.0*numpy.degrees(centerPupil.getX())
                yCenter = 3600.0*numpy.degrees(centerPupil.getY())
                xMin = 3600.0*numpy.degrees(xmin)
                xMax = 3600.0*numpy.degrees(xmax)
                yMin = 3600.0*numpy.degrees(ymin)
                yMax = 3600.0*numpy.degrees(ymax)
                plateScale = 3600.0*numpy.degrees(plateScale)

                detector = GalSimDetector(name=dd.getName(), xCenter=xCenter, yCenter=yCenter,
                                          xMin=xMin, yMin=yMin, xMax=xMax, yMax=yMax,
                                          plateScale=plateScale)

                detectors.append(detector)

            if self.bandpassDict is None:
                self.loadBandpassesFromFiles(bandpassNames=self.bandpassNames,
                                             filedir=self.bandpassDir,
                                             bandpassRoot=self.bandpassRoot,
                                             componentList=self.componentList,
                                             skyBandpass=self.skyBandpassName,
                                             skySED=self.skySEDname)

            self.galSimInterpreter = GalSimInterpreter(detectors=detectors, bandpassDict=self.bandpassDict,
                                                       gain=self.gain, m5Dict=m5Dict,
                                                       noiseWrapper=self.noise_and_background)

            self.galSimInterpreter.setPSF(PSF=self.PSF)


    def write_images(self, nameRoot=None):
        """
        Writes the FITS images associated with this InstanceCatalog.

        Cannot be called before write_catalog is called.

        @param [in] nameRoot is an optional string prepended to the names
        of the FITS images.  The FITS images will be named

        @param [out] namesWritten is a list of the names of the FITS files generated

        nameRoot_DetectorName_FilterName.fits

        (e.g. myImages_R_0_0_S_1_1_y.fits for an LSST-like camera with
        nameRoot = 'myImages')
        """
        namesWritten = self.galSimInterpreter.writeImages(nameRoot=nameRoot)

        return namesWritten

class GalSimGalaxies(GalSimBase, AstrometryGalaxies, EBVmixin):
    """
    This is a GalSimCatalog class for galaxy components (i.e. objects that are shaped
    like Sersic profiles).

    See the docstring in GalSimBase for explanation of how this class should be used.
    """

    catalog_type = 'galsim_galaxy'
    galsim_type = 'sersic'
    default_columns = [('galacticAv', 0.1, float),
                       ('galSimType', 'sersic', (str,6))]

class GalSimAgn(GalSimBase, AstrometryGalaxies, EBVmixin):
    """
    This is a GalSimCatalog class for AGN.

    See the docstring in GalSimBase for explanation of how this class should be used.
    """
    catalog_type = 'galsim_agn'
    galsim_type = 'pointSource'
    default_columns = [('galacticAv', 0.1, float),
                      ('galSimType', 'pointSource', (str,11)),
                      ('majorAxis', 0.0, float),
                      ('minorAxis', 0.0, float),
                      ('sindex', 0.0, float),
                      ('positionAngle', 0.0, float),
                      ('halfLightRadius', 0.0, float),
                      ('internalAv', 0.0, float),
                      ('internalRv', 0.0, float)]

class GalSimStars(GalSimBase, AstrometryStars, EBVmixin):
    """
    This is a GalSimCatalog class for stars.

    See the docstring in GalSimBase for explanation of how this class should be used.
    """
    catalog_type = 'galsim_stars'
    galsim_type = 'pointSource'
    default_columns = [('galacticAv', 0.1, float),
                      ('galSimType', 'pointSource', (str,11)),
                      ('internalAv', 0.0, float),
                      ('internalRv', 0.0, float),
                      ('redshift', 0.0, float),
                      ('majorAxis', 0.0, float),
                      ('minorAxis', 0.0, float),
                      ('sindex', 0.0, float),
                      ('positionAngle', 0.0, float),
                      ('halfLightRadius', 0.0, float)]
