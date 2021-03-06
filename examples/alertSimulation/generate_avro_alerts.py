import numpy as np
import multiprocessing as mproc
import os
from lsst.sims.catUtils.utils import ObservationMetaDataGenerator
from lsst.sims.catUtils.utils import AlertDataGenerator

from lsst.utils import getPackageDir
from lsst.sims.utils.CodeUtilities import sims_clean_up

from lsst.sims.catUtils.utils import AvroAlertGenerator
import time

import argparse

def process_obshistid(obshistid_list, in_dir, sql_prefix_list,
                      obshistid_to_htmid, out_dir, out_prefix,
                      schema_dir, dmag_cutoff, log_file_name, lock):

    avro_gen = AvroAlertGenerator()
    avro_gen.load_schema(schema_dir)

    for obshistid in obshistid_list:
        htmid_list = obshistid_to_htmid[obshistid]
        avro_gen.write_alerts(obshistid, in_dir, sql_prefix_list,
                              htmid_list, out_dir, out_prefix, dmag_cutoff,
                              lock=lock, log_file_name=log_file_name)

if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument('--n_proc', type=int, default=1,
                        help='Number of independent processes to start')
    parser.add_argument('--log_file', type=str, default=None,
                        help='Name of file to write progress to')
    parser.add_argument('--night0', type=int, default=30,
                        help='First night of survey to simulate (default=30)')
    parser.add_argument('--night1', type=int, default=61,
                        help='Last night of survey to simulate (default=61)')
    parser.add_argument('--in_dir', type=str, default=None,
                        help='Directory containing sqlite files created '
                        'by AlertDataGenerator')
    parser.add_argument('--out_dir', type=str, default=None,
                        help='Directory in which to write avro files')
    parser.add_argument('--out_prefix', type=str, default=None,
                        help='Prefix of avro file names')
    parser.add_argument('--dmag_cutoff', type=float, default=0.005,
                        help='Minimum delta magnitude to trigger an alert '
                        '(default=0.005)')
    parser.add_argument('--schema_dir', type=str, default=None,
                        help='Directory containing avro schemas')
    parser.add_argument('--opsim_db', type=str,
                        default=os.path.join('/local', 'lsst', 'danielsf',
                                             'OpSimData', 'minion_1016_sqlite.db'),
                        help='Path to OpSim database used for survey cadence')


    args = parser.parse_args()

    if args.in_dir is None:
        raise RuntimeError("You must specify in_dir")
    if args.out_dir is None:
        raise RuntimeError("You must specify out_dir")
    if args.out_prefix is None:
        raise RuntimeError("You must specify out_prefix")
    if args.schema_dir is None:
        raise RuntimeError("You must specify schema_dir")

    if args.log_file is not None:
        if os.path.exists(args.log_file):
            raise RuntimeError("%s already exists" % args.log_file)

    if os.path.exists(args.out_dir):
        if not os.path.isdir(args.out_dir):
            raise RuntimeError("%s is not a directory" % args.out_dir)

    if not os.path.exists(args.out_dir):
        os.mkdir(args.out_dir)

    t_start = time.time()
    # get list of ObservationMetaData to simulate
    obs_gen = ObservationMetaDataGenerator(args.opsim_db, driver='sqlite')
    obs_list = obs_gen.getObservationMetaData(night=15)

    del obs_gen
    sims_clean_up()

    print('%d obs' % len(obs_list))

    # use AlertDataGenerator to separate the ObservationMetaData
    # by htmid
    alert_gen = AlertDataGenerator()
    alert_gen.subdivide_obs(obs_list, htmid_level=6)

    # Create a dict that maps an obsHistID to the list of htmids
    # of the trixels overlapping that observation
    #
    # Also separate list of obsHistIDs into n_proc
    # lists of roughly balanced loads.
    obshistid_to_htmid = {}
    obshistid_list = []
    for i_proc in range(args.n_proc):
        obshistid_list.append([])

    i_proc = 0
    for htmid in alert_gen.htmid_list:
        for obs in alert_gen.obs_from_htmid(htmid):

            obshistid = obs.OpsimMetaData['obsHistID']

            if obshistid not in obshistid_to_htmid:
                obshistid_to_htmid[obshistid] = []
                obshistid_list[i_proc].append(obshistid)
                i_proc += 1
                if i_proc >= args.n_proc:
                    i_proc = 0

            obshistid_to_htmid[obshistid].append(htmid)

    # make sure to process both stellar and agn alert data
    sql_prefix_list = ['stellar', 'agn']

    # start independent processes
    if args.n_proc == 1:
        process_obshistid(obshistid_list[0], args.in_dir,
                          sql_prefix_list,
                          obshistid_to_htmid, args.out_dir,
                          args.out_prefix,
                          args.schema_dir, args.dmag_cutoff,
                          args.log_file, None)
    else:
        lock = mproc.Lock()
        p_list = []

        for i_proc in range(args.n_proc):
            p = mproc.Process(target=process_obshistid,
                              args=(obshistid_list[i_proc], args.in_dir,
                                    sql_prefix_list, obshistid_to_htmid,
                                    args.out_dir, args.out_prefix,
                                    args.schema_dir, args.dmag_cutoff,
                                    args.log_file, lock))
            p.start()
            p_list.append(p)

        for p in p_list:
            p.join()

    elapsed = (time.time()-t_start)/3600.0
    print('all done; %.2e hrs' % elapsed)
