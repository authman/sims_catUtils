import os
import numpy
import galsim
from lsst.sims.photUtils import Sed, Bandpass

class GalSimDetector(object):
    def __init__(self, name=None, xCenter=None, yCenter=None,
                 xMin=None, xMax=None, yMin=None, yMax=None):
    
        self.name = name
        self.xCenter = xCenter
        self.yCenter = yCenter
        self.xMin = xMin
        self.xMax = xMax
        self.yMin = yMin
        self.yMax = yMax

class GalSimInterpreter(object):

    def __init__(self, scale=0.2):
        self.imsimband = Bandpass()
        self.imsimband.imsimBandpass()
        self.scale = scale
        self.bigfft = galsim.GSParams(maximum_fft_size=10000)
        self.sedDir = os.getenv('SIMS_SED_LIBRARY_DIR')
        self.data = None
        self.detectors = []
        
    def readCatalog(self, catalogFile):
        dataNeeded = ['x_pupil', 'y_pupil', 'magNorm', 'sedFilepath',
                      'redshift', 'positionAngle',
                      'galacticAv', 'galacticRv', 'internalAv', 'internalRv',
                      'majorAxis', 'minorAxis', 'sindex', 'halfLightRadius']

        dataTypes={
                   'x_pupil':float, 'y_pupil':float, 'magNorm':float, 'chipName':(str, 126),
                   'sedFilepath':(str,126), 'redshift':float, 'positionAngle': float,
                   'galacticAv':float, 'galacticRv':float, 'internalAv':float,
                   'internalRv':float, 'majorAxis':float, 'minorAxis':float,
                   'sindex':float, 'halfLightRadius':float, 'galSimType':(str,126)
                   }

        defaultType = (str,126)

        cat = open(catalogFile,'r')
        lines = cat.readlines()
        cat.close()
        
        for line in lines:
            if line[0] != '#':
                break
       
            line = line.replace("#","").strip()
            line = numpy.array(line.split(';'))
            
            if line[0] == 'galSimType':
                dtype = numpy.dtype(
                        [(ww, dataTypes[ww]) if ww in dataTypes else (ww, defaultType) for ww in line]
                        )
                        
            if line[0] == 'detector':
                name = line[1]
                xCenter = float(line[2])
                yCenter = float(line[3])
                xMin = float(line[4])
                xMax = float(line[5])
                yMin = float(line[6])
                yMax = float(line[7])
                
                detector = GalSimDetector(name=name, xCenter=xCenter, yCenter=yCenter,
                                          xMin=xMin, xMax=xMax, yMin=yMin, yMax=yMax)
                self.detectors.append(detector)
        
        print 'n_detectors ',len(self.detectors)
        self.data = numpy.genfromtxt(catalogFile, dtype=dtype, delimiter=';')
    
    def drawCatalog(self, fileNameRoot=None, bandPass=None):
        for detector in self.detectors:
            self.drawImage(fileNameRoot=fileNameRoot, bandPass=bandPass, detector=detector)
    
    def drawImage(self, fileNameRoot=None, bandPass=None, detector=None):
        self.bandPass = galsim.Bandpass(bandPass)
        
        detectorName = detector.name
        detectorName = detectorName.replace(',','_')
        detectorName = detectorName.replace(':','_')
        detectorName = detectorName.replace(' ','_')
        
        fileName = fileNameRoot+detectorName+'.fits'
        
        nx = int((detector.xMax - detector.xMin)/self.scale)
        ny = int((detector.yMax - detector.yMin)/self.scale)
        image = galsim.Image(nx,ny)
        
        drawn = 0
        if self.data is not None:
            for entry in self.data:
                if entry['chipName'] == detector.name:
                    drawn += 1
                    print entry
                    if entry['chipName'] != detector.name:
                        print 'WARNING wrong chip ',entry['chipName'],detectorName
                        exit()

                    if entry['galSimType'] == 'galaxy':
                        print 'drawing'
                        self.drawGalaxy(entry=entry, image=image, detector=detector)
                    else:
                        print entry['galSimType']
        
        if drawn>0:
            image.write(fileName)
        
    def drawGalaxy(self, entry=None, image=None, detector=None):

        sedFile = os.path.join(self.sedDir,entry['sedFilepath'])
        
        obj = galsim.Sersic(n=entry['sindex'], half_light_radius=entry['halfLightRadius'],
                            gsparams=self.bigfft)
        
        obj = obj.shear(q=entry['minorAxis']/entry['majorAxis'], beta=entry['positionAngle']*galsim.radians)
    
        dx=entry['x_pupil']-detector.xCenter
        dy=entry['y_pupil']-detector.yCenter
    
        obj = obj.shift(dx, dy)
                         
        sed = Sed()
        sed.readSED_flambda(sedFile)
        fNorm = sed.calcFluxNorm(entry['magNorm'], self.imsimband)
        sed.multiplyFluxNorm(fNorm)
        a_int, b_int = sed.setupCCMab()
        sed.addCCMDust(a_int, b_int, A_v=entry['internalAv'], R_v=entry['internalRv'])
        sed.redshiftSED(entry['redshift'], dimming=False)
        sed.addCCMDust(a_int, b_int, A_v=entry['galacticAv'], R_v=entry['galacticRv'])
        
        spectrum = galsim.SED(spec = lambda ll:
                                 numpy.interp(ll, sed.wavelen, sed.flambda),
                                 flux_type='flambda')
        
        obj = obj*spectrum
        
        image = obj.drawImage(bandpass=self.bandPass, scale=self.scale, image=image,
                                  add_to_image=True, method='real_space')
 


bandPass = os.path.join(os.getenv('THROUGHPUTS_DIR'),'baseline','total_g.dat')

gs = GalSimInterpreter()
gs.readCatalog('galsim_example.txt')

name = 'galsimTest_'
gs.drawCatalog(bandPass=bandPass, fileNameRoot=name)
 