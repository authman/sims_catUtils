from lsst.sims.catalogs.generation.db import DBObject, ObservationMetaData
#The following is to get the object ids in the registry
import lsst.sims.catUtils.baseCatalogModels as bcm
from lsst.sims.catUtils.exampleCatalogDefinitions import RefCatalogGalaxyBase

if __name__ == '__main__':
    obs_metadata = ObservationMetaData(circ_bounds=dict(ra=0., dec=0., radius=0.1))
    dbobj = DBObject.from_objid('galaxyBase')
    t = dbobj.getCatalog('galaxy_photometry_cat', obs_metadata=obs_metadata)
    filename = 'tmp.dat'
    t.write_catalog(filename, chunk_size=100000)

