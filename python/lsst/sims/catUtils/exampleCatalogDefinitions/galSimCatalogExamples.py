"""
The catalog examples in this file will write catalog files that can be read
by galSimInterpreter.py (to be written), which will use galSim to turn them
into an image.
"""

import numpy
from lsst.sims.catalogs.measures.instance import InstanceCatalog, cached
from lsst.sims.coordUtils import CameraCoords, AstrometryGalaxies
from lsst.sims.photUtils import EBVmixin
import lsst.afw.cameraGeom.testUtils as camTestUtils
from lsst.afw.cameraGeom import PUPIL, PIXELS, FOCAL_PLANE
from lsst.obs.lsstSim import LsstSimMapper

__all__ = ["GalSimGalaxies"]

def radiansToArcsec(value):
    return 3600.0*numpy.degrees(value)

class GalSimBase(InstanceCatalog, CameraCoords):

    cannot_be_null = ['sedFilepath']

    column_outputs = ['galSimType', 'chipName', 'x_pupil', 'y_pupil', 'sedFilepath', 'magNorm',
                      'majorAxis', 'minorAxis', 'sindex', 'halfLightRadius',
                      'positionAngle', 'redshift',
                      'internalAv', 'internalRv', 'galacticAv', 'galacticRv']

    transformations = {'x_pupil':radiansToArcsec,
                       'y_pupil':radiansToArcsec}
    default_formats = {'S':'%s', 'f':'%.9g', 'i':'%i'}

    delimiter = ';'

    #camera = LsstSimMapper().camera
    camera = camTestUtils.CameraWrapper().camera

    def get_sedFilepath(self):
        return numpy.array([self.specFileMap[k] if self.specFileMap.has_key(k) else None
                         for k in self.column_by_name('sedFilename')])

    def write_header(self, file_handle):

        for dd in self.camera:
            cs = dd.makeCameraSys(PUPIL)
            center = self.camera.transform(dd.getCenter(FOCAL_PLANE),cs).getPoint()
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

            xcenter = 3600.0*numpy.degrees(center.getX())
            ycenter = 3600.0*numpy.degrees(center.getY())
            xmin = 3600.0*numpy.degrees(xmin)
            xmax = 3600.0*numpy.degrees(xmax)
            ymin = 3600.0*numpy.degrees(ymin)
            ymax = 3600.0*numpy.degrees(ymax)

            file_handle.write('#detector;%s;%f;%f;%f;%f;%f;%f\n' %
                             (dd.getName(), xcenter, ycenter, xmin, xmax, ymin, ymax))

        InstanceCatalog.write_header(self, file_handle)

class GalSimGalaxies(GalSimBase, AstrometryGalaxies, EBVmixin):
    catalog_type = 'galsim_galaxy'
    default_columns = [('galacticAv', 0.1, float),
                       ('galSimType', 'galaxy', (str,6))]