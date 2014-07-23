"""
This file shows how to generate a phoSim input catalog named phoSim_example.txt

"""

from __future__ import with_statement
from lsst.sims.catalogs.measures.instance import InstanceCatalog
from lsst.sims.catalogs.generation.db import DBObject, ObservationMetaData
from lsst.sims.catUtils.exampleCatalogDefinitions.phoSimCatalogExamples import \
        PhoSimCatalogPoint, PhoSimCatalogSersic2D, PhoSimCatalogZPoint

from lsst.sims.catUtils.baseCatalogModels import *

starObjNames = ['msstars', 'bhbstars', 'wdstars', 'rrlystars', 'cepheidstars']

obsMD = DBObject.from_objid('opsim3_61')
obs_metadata = obsMD.getObservationMetaData(88625744, 0.33, makeCircBounds = True)

doHeader= True
for starName in starObjNames:
    stars = DBObject.from_objid(starName)
    star_phoSim=PhoSimCatalogPoint(stars,obs_metadata=obs_metadata)
    if (doHeader):
        with open("phoSim_example.txt","w") as fh:
            star_phoSim.write_header(fh)
        doHeader = False

    #below, write_header=Fales prevents the code from overwriting the header just written
    #write_mode = 'a' allows the code to append the new objects to the output file, rather
    #than overwriting the file for each different class of object.    
    star_phoSim.write_catalog("phoSim_example.txt",write_mode='a',write_header=False,chunk_size=20000)

gals = DBObject.from_objid('galaxyBulge')
galaxy_phoSim = PhoSimCatalogSersic2D(gals, obs_metadata=obs_metadata,constraint="sedname_bulge is not NULL")
galaxy_phoSim.write_catalog("phoSim_example.txt",write_mode='a',write_header=False,chunk_size=20000)

gals = DBObject.from_objid('galaxyDisk')
galaxy_phoSim = PhoSimCatalogSersic2D(gals, obs_metadata=obs_metadata,constraint="sedname_disk is not NULL")
galaxy_phoSim.write_catalog("phoSim_example.txt",write_mode='a',write_header=False,chunk_size=20000)

gals = DBObject.from_objid('galaxyAgn')
galaxy_phoSim = PhoSimCatalogZPoint(gals, obs_metadata=obs_metadata,constraint="sedname_agn is not NULL")
galaxy_phoSim.write_catalog("phoSim_example.txt",write_mode='a',write_header=False,chunk_size=20000)



