from lsst.sims.catalogs.generation.db import DBObject, ObservationMetaData
class StarBase(DBObject):
    objid = 'starbase'
    tableid = None
    idColKey = 'id'
    raColName = 'ra'
    decColName = 'decl'
    objectTypeId = -1
    spatialModel = 'POINT'
    #Don't run test on base class
    doRunTest = False
    #default observation metadata
    testObservationMetaData = ObservationMetaData(circ_bounds=dict(ra=210., dec=-30., radius=0.3),
                                                  mjd=52000., bandpassName='g')
    dbDefaultValues = {'varsimobjid':-1, 'runid':-1, 'ismultiple':-1, 'run':-1,
                       'runobjid':-1}
    #These types should be matched to the database.
    #: Default map is float.  If the column mapping is the same as the column name, None can be specified
    columns = [('id','simobjid', int),
               ('raJ2000', 'ra*PI()/180.'),
               ('decJ2000', 'decl*PI()/180.'),
               ('glon', 'gal_l*PI()/180.'),
               ('glat', 'gal_b*PI()/180.'),
               ('magNorm', '(-2.5*log(flux_scale)/log(10.)) - 18.402732642'),
               ('properMotionRa', '(mudecl/(1000.*3600.))*PI()/180.'),
               ('properMotionDec', '(mura/(1000.*3600.))*PI()/180.'),
               ('galacticAv', 'CONVERT(float, ebv*3.1)'),
               ('radialVelocity', 'vrad'),
               ('variabilityParameters', 'varParamStr', str, 256),
               ('sedFilename', 'sedfilename', unicode, 40)]

class StarObj(StarBase):
    objid = 'allstars'
    tableid = 'starsALL_forceseek'
    objectTypeId = 4
    doRunTest = True
    testObservationMetaData = ObservationMetaData(circ_bounds=dict(ra=210., dec=-30., radius=0.1),
                                                  mjd=52000., bandpassName='g')
    #These types should be matched to the database.
    #: Default map is float.  If the column mapping is the same as the column name, None can be specified
    columns = [('id','simobjid', int),
               ('raJ2000', 'ra*PI()/180.'),
               ('decJ2000', 'decl*PI()/180.'),
               ('glon', 'gal_l*PI()/180.'),
               ('glat', 'gal_b*PI()/180.'),
               ('magNorm', '(-2.5*log(flux_scale)/log(10.)) - 18.402732642'),
               ('properMotionRa', '(mudecl/(1000.*3600.))*PI()/180.'),
               ('properMotionDec', '(mura/(1000.*3600.))*PI()/180.'),
               ('galacticAv', 'CONVERT(float, ebv*3.1)'),
               ('radialVelocity', 'vrad'),
               ('variabilityParameters', 'varParamStr', str, 256),
               ('sedFilename', 'sedfilename', unicode, 40)]

class MsStarObj(StarBase):
    objid = 'msstars'
    tableid = 'starsMSRGB_forceseek'
    objectTypeId = 5
    doRunTest = True
    testObservationMetaData = ObservationMetaData(circ_bounds=dict(ra=210., dec=-30., radius=0.1),
                                                  mjd=52000., bandpassName='g')
    #These types should be matched to the database.
    #: Default map is float.  If the column mapping is the same as the column name, None can be specified
    columns = [('id','simobjid', int),
               ('raJ2000', 'ra*PI()/180.'),
               ('decJ2000', 'decl*PI()/180.'),
               ('glon', 'gal_l*PI()/180.'),
               ('glat', 'gal_b*PI()/180.'),
               ('magNorm', '(-2.5*log(flux_scale)/log(10.)) - 18.402732642'),
               ('properMotionRa', '(mudecl/(1000.*3600.))*PI()/180.'),
               ('properMotionDec', '(mura/(1000.*3600.))*PI()/180.'),
               ('galacticAv', 'CONVERT(float, ebv*3.1)'),
               ('radialVelocity', 'vrad'),
               ('variabilityParameters', 'varParamStr', str, 256),
               ('sedFilename', 'sedfilename', unicode, 40)]

class WdStarObj(StarBase):
    objid = 'wdstars'
    tableid = 'starsWD'
    objectTypeId = 6
    doRunTest = True
    #These types should be matched to the database.
    #: Default map is float.  If the column mapping is the same as the column name, None can be specified
    columns = [('id','simobjid', int),
               ('raJ2000', 'ra*PI()/180.'),
               ('decJ2000', 'decl*PI()/180.'),
               ('glon', 'gal_l*PI()/180.'),
               ('glat', 'gal_b*PI()/180.'),
               ('magNorm', '(-2.5*log(flux_scale)/log(10.)) - 18.402732642'),
               ('properMotionRa', '(mudecl/(1000.*3600.))*PI()/180.'),
               ('properMotionDec', '(mura/(1000.*3600.))*PI()/180.'),
               ('galacticAv', 'CONVERT(float, ebv*3.1)'),
               ('radialVelocity', 'vrad'),
               ('variabilityParameters', 'varParamStr', str, 256),
               ('sedFilename', 'sedfilename', unicode, 40)]

class RRLyStarObj(StarBase):
    objid = 'rrlystars'
    tableid = 'starsRRLy'
    objectTypeId = 7
    doRunTest = True
    #These types should be matched to the database.
    #: Default map is float.  If the column mapping is the same as the column name, None can be specified
    columns = [('id','simobjid', int),
               ('raJ2000', 'ra*PI()/180.'),
               ('decJ2000', 'decl*PI()/180.'),
               ('glon', 'gal_l*PI()/180.'),
               ('glat', 'gal_b*PI()/180.'),
               ('magNorm', '(-2.5*log(flux_scale)/log(10.)) - 18.402732642'),
               ('properMotionRa', '(mudecl/(1000.*3600.))*PI()/180.'),
               ('properMotionDec', '(mura/(1000.*3600.))*PI()/180.'),
               ('galacticAv', 'CONVERT(float, ebv*3.1)'),
               ('radialVelocity', 'vrad'),
               ('variabilityParameters', 'varParamStr', str, 256),
               ('sedFilename', 'sedfilename', unicode, 40)]

class BhbStarObj(StarBase):
    objid = 'bhbstars'
    tableid = 'starsBHB'
    objectTypeId = 8
    doRunTest = True
    #These types should be matched to the database.
    #: Default map is float.  If the column mapping is the same as the column name, None can be specified
    columns = [('id','simobjid', int),
               ('raJ2000', 'ra*PI()/180.'),
               ('decJ2000', 'decl*PI()/180.'),
               ('glon', 'gal_l*PI()/180.'),
               ('glat', 'gal_b*PI()/180.'),
               ('magNorm', '(-2.5*log(flux_scale)/log(10.)) - 18.402732642'),
               ('properMotionRa', '(mudecl/(1000.*3600.))*PI()/180.'),
               ('properMotionDec', '(mura/(1000.*3600.))*PI()/180.'),
               ('galacticAv', 'CONVERT(float, ebv*3.1)'),
               ('radialVelocity', 'vrad'),
               ('variabilityParameters', 'varParamStr', str, 256),
               ('sedFilename', 'sedfilename', unicode, 40)]

class EbStarObj(StarBase):
    objid = 'ebstars'
    tableid = 'ebstars'
    objectTypeId = 9
    doRunTest = True
    testObservationMetaData = ObservationMetaData(circ_bounds=None,
                                                  mjd=52000., bandpassName='g')
    #These types should be matched to the database.
    #: Default map is float.  If the column mapping is the same as the column name, None can be specified
    columns = [('id','simobjid', int),
               ('raJ2000', 'ra*PI()/180.'),
               ('decJ2000', 'decl*PI()/180.'),
               ('glon', 'gal_l*PI()/180.'),
               ('glat', 'gal_b*PI()/180.'),
               ('magNorm', '(-2.5*log(flux_scale)/log(10.)) - 18.402732642'),
               ('properMotionRa', '(mudecl/(1000.*3600.))*PI()/180.'),
               ('properMotionDec', '(mura/(1000.*3600.))*PI()/180.'),
               ('galacticAv', 'CONVERT(float, ebv*3.1)'),
               ('radialVelocity', 'vrad'),
               ('variabilityParameters', 'varParamStr', str, 256),
               ('sedFilename', 'sedfilename', unicode, 40)]

class CepheidStarObj(StarBase):
    objid = 'cepheidstars'
    tableid = 'cepheidstars'
    objectTypeId = 10
    doRunTest = True
    testObservationMetaData = ObservationMetaData(circ_bounds=None,
                                                  mjd=52000., bandpassName='g')
    #These types should be matched to the database.
    #: Default map is float.  If the column mapping is the same as the column name, None can be specified
    columns = [('id','simobjid', int),
               ('raJ2000', 'ra*PI()/180.'),
               ('decJ2000', 'decl*PI()/180.'),
               ('glon', 'gal_l*PI()/180.'),
               ('glat', 'gal_b*PI()/180.'),
               ('magNorm', '(-2.5*log(flux_scale)/log(10.)) - 18.402732642'),
               ('properMotionRa', '(mudecl/(1000.*3600.))*PI()/180.'),
               ('properMotionDec', '(mura/(1000.*3600.))*PI()/180.'),
               ('galacticAv', 'CONVERT(float, ebv*3.1)'),
               ('radialVelocity', 'vrad'),
               ('variabilityParameters', 'varParamStr', str, 256),
               ('sedFilename', 'sedfilename', unicode, 40)]

class EasterEggStarObj(StarBase):
    objid = 'eastereggstars'
    tableid = 'AstromEasterEggs'
    objectTypeId = 11
    doRunTest = True
    testObservationMetaData = ObservationMetaData(circ_bounds=None,
                                                  mjd=52000., bandpassName='g')
    dbDefaultValues = StarBase.dbDefaultValues
    dbDefaultValues['sedid']=-1
    dbDefaultValues['especid']=-1
    dbDefaultValues['pop']=-1
    dbDefaultValues['type']=-1
    dbDefaultValues['isvar']=False
    #These types should be matched to the database.
    #: Default map is float.  If the column mapping is the same as the column name, None can be specified
    columns = [('id','simobjid', int),
               ('raJ2000', 'ra*PI()/180.'),
               ('decJ2000', 'decl*PI()/180.'),
               ('glon', 'gal_l*PI()/180.'),
               ('glat', 'gal_b*PI()/180.'),
               ('magNorm', '(-2.5*log(flux_scale)/log(10.)) - 18.402732642'),
               ('properMotionRa', '(mudecl/(1000.*3600.))*PI()/180.'),
               ('properMotionDec', '(mura/(1000.*3600.))*PI()/180.'),
               ('galacticAv', 'CONVERT(float, ebv*3.1)'),
               ('radialVelocity', 'vrad'),
               ('variabilityParameters', 'varParamStr', str, 256),
               ('sedFilename', 'sedfilename', unicode, 40)]

class DwarfGalStarObj(StarBase):
    objid = 'dwarfgalstars'
    tableid = 'dwarfGalaxies'
    objectTypeId = 12
    doRunTest = True
    testObservationMetaData = ObservationMetaData(circ_bounds={'ra':2., 'dec':-0.3, 'radius':0.1},
                                                  mjd=52000., bandpassName='g')
    #These types should be matched to the database.
    #: Default map is float.  If the column mapping is the same as the column name, None can be specified
    columns = [('id','simobjid', int),
               ('raJ2000', 'ra*PI()/180.'),
               ('decJ2000', 'decl*PI()/180.'),
               ('glon', 'gal_l*PI()/180.'),
               ('glat', 'gal_b*PI()/180.'),
               ('magNorm', '(-2.5*log(flux_scale)/log(10.)) - 18.402732642'),
               ('properMotionRa', '(mudecl/(1000.*3600.))*PI()/180.'),
               ('properMotionDec', '(mura/(1000.*3600.))*PI()/180.'),
               ('galacticAv', 'CONVERT(float, ebv*3.1)'),
               ('radialVelocity', 'vrad'),
               ('variabilityParameters', 'varParamStr', str, 256),
               ('sedFilename', 'sedfilename', unicode, 40)]
