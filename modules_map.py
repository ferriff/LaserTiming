import pandas as pd
import warnings
warnings.simplefilter(action='ignore', category=pd.errors.PerformanceWarning)

import os.path
import numpy as np
from pathlib import Path

import sys
sys.path.append('../')
import shutil

from elmonk.dst import DstReader ### to read the DST files into pandas
import matplotlib.pyplot as plt

from elmonk.common import HdfLaser
from elmonk.common.helper import scalar_to_list, make_index
import seaborn as sns

import ecalic

import argparse
from tqdm import tqdm

parser = argparse.ArgumentParser(description='Command line parser of plotting options')

parser.add_argument('--fed', dest='fed',type=int, help='fed', default=612)
parser.add_argument('--single', dest='single', help='write single sequence and run', action='store_true')

args = parser.parse_args()

FED = args.fed

year = 2018
basedir = Path(f'/eos/cms/store/group/dpg_ecal/alca_ecalcalib/laser/dst.hdf')

workdir = "/afs/cern.ch/work/c/camendol/LaserData/"+str(year)+"/tables/"
filename = workdir + "FED_"+str(FED)+".hdf"

print(filename)                                                                                                                        
#if True:
if (not os.path.isfile(filename)): 
    data = HdfLaser(basedir / f'{year}/dstUL_db.{year}.hdf5')
    period = [f'{year}-06-01',f'{year}-09-01']
    
    #mask 2018
    #status = ecalic.xml('../elmonk/etc/data/ecalChannelStatus_run324773.xml',type='status').icCMS()
    #good_channels = status.iov.mask(status['ic']!=0).dropna(how='all')

    xtals = data.xtal_idx('FED == '+str(FED))
    histories = data.xtal_history(iov_idx=data.iov_idx(period),xtal_idx=xtals, xtal_property='tAPD')

    run_seq = data.iov_idx_to_run_seq(data.iov_idx(period)['iov_idx'].values)
    histories[["run","seq"]] = np.array(run_seq)
    histories = histories.reset_index().set_index(["date", "run", "seq"])
    histories.to_hdf(filename, key= "hist", mode = "w")

else: 
    histories = pd.read_hdf(filename,key = "hist", mode = "r")


histories = histories.reset_index().set_index(["date","seq","run"])
histories = histories.T.reset_index()


histories['ieta']    = histories.set_index('xtal_ecalic_id').index.map(ecalic.geom.ix) 
histories['iphi']    = histories.set_index('xtal_ecalic_id').index.map(ecalic.geom.iy) 

#add sides mask
side1 = (((histories['ieta'] > 0) & (histories['ieta'] > 4) & (histories['iphi'].mod(20) > 10)) | ((histories['ieta'] < 0) & (histories['ieta'] < - 5) & ((histories['iphi']-1).mod(20) + 1 < 11)))
histories['side'] = np.where(side1, 1, 0)

#make xtal_id as defined in dst files 
histories['TT']      = histories.set_index('xtal_ecalic_id').index.map(ecalic.geom.ccu) 
histories['strip']   = histories.set_index('xtal_ecalic_id').index.map(ecalic.geom.strip) 
histories['Xtal']    = histories.set_index('xtal_ecalic_id').index.map(ecalic.geom.Xtal) 
histories["xtal_id"] = (histories['TT'] - 1) * 25 + (histories['strip'] - 1) * 5 + histories['Xtal'] - 1

#histories: t_xtal, full runs
histories = histories.reset_index().set_index(["ieta", "iphi", "xtal_id", "side"])
histories = histories.drop(columns=['TT', 'strip','Xtal', 'xtal_ecalic_id','index'])

histories = histories.T

#get matacq tstart
matacq = pd.read_hdf((basedir / f'{year}/dstUL_db.{year}.hdf5'), 'Matacq')
matacq = matacq[(matacq["FED"] == FED)]

histories["tstart0"]  = histories.reset_index().set_index(["run","seq"]).index.map(matacq[(matacq["side"] == 0)].set_index(["run", "seq"]).tstart)
histories["tstart1"]  = histories.reset_index().set_index(["run","seq"]).index.map(matacq[(matacq["side"] == 1)].set_index(["run", "seq"]).tstart)


#convert to ns and subtract matacq for side 1 and 0 
histories.iloc[:, :-2] = histories.iloc[:, :-2] * 25 #conv times to ns (except for matacq columns)
idx = pd.IndexSlice
histories.loc[:, idx[:,:,:,(histories.columns.get_level_values('side') == 1)]] = histories.sub(histories.tstart1, axis = 0) + 1390 
print(histories)
histories.loc[:, idx[:,:,:,(histories.columns.get_level_values('side') == 0)]] = histories.sub(histories.tstart0, axis = 0) + 1390 
histories = histories.drop(columns = ["tstart1", "tstart0"])
print(histories)


if args.single:
    #write indivitual .txt files for each
    list_groups = []

    first_run = histories.reset_index().run.tolist()[0]
    first = histories.copy().reset_index()
    first = first[((first["run"] == first_run) & (first["seq"] == 0))]
    first = first.set_index("date","run")

    with tqdm(total=histories.groupby("run").ngroups, unit='entries') as pbar:
        for run, rgroup in histories.groupby("run"):
            rgroup = rgroup.reset_index().set_index("date","run")
            #rgroup = rgroup.T.sub(first.T[first.T.columns[0]], axis = 0).T #for subtracting first tMax of the year
            #rgroup["run"] = run
            list_groups.append(rgroup)
            if not os.path.exists("/eos/home-c/camendol/www/LaserTiming/blue_FEDs_sub/"+str(FED)):
                os.makedirs("/eos/home-c/camendol/www/LaserTiming/blue_FEDs_sub/"+str(FED))
                shutil.copy("/eos/home-c/camendol/www/index.php","/eos/home-c/camendol/www/LaserTiming/"+str(FED))
                shutil.copy("/eos/home-c/camendol/www/index.php","/eos/home-c/camendol/www/LaserTiming/blue_FEDs_sub/"+str(FED))
            for seq, sgroup in rgroup.groupby("seq"):
                sgroup = sgroup.reset_index().set_index("date").drop(columns=['seq','run']).T.reset_index()
                sgroup = sgroup.astype({"iphi": "int", "ieta":"int", sgroup.columns[-1] : "float"})
                sgroup.pivot_table(columns = "iphi", index = "ieta", values = sgroup.columns[-1]).to_csv("/eos/home-c/camendol/www/LaserTiming/blue_FEDs_sub/"+str(FED)+"/"+str(FED)+"_"+str(run)+"_"+str(seq)+".txt")
                list_groups.append(sgroup)

            pbar.update(1)

    del list_groups


histories = histories.reset_index().set_index("date").drop(columns=['seq','run']).T

histories = histories.where(histories.std(axis=1) > 1)
histories = histories.where(histories.std(axis=1) < 50)

histories["mean"] = histories.mean(axis=1)
histories["RMS"]  = histories.std(axis=1)
histories["min"]  = histories.min(axis=1)
histories["max"]  = histories.max(axis=1)


histories = histories.reset_index()

trimmed = histories[["xtal_id", "mean", "RMS", "min", "max", "ieta", "iphi"]]
    
print(trimmed)

for var in ["min","max", "RMS", "mean"]:
    plt.figure(figsize=(7,20))
    ax = sns.heatmap(trimmed.pivot_table(columns = "iphi", index = "ieta", values = var, cbar_kws={'label': var+"t$_{xtal}$"}).sort_index(ascending = True))
    #plt.xticks(np.arange(trimmed.ieta.min(), trimmed.ieta.max()+1, 5))
    ax.set(xlabel='i$\phi$', ylabel='i$\eta$')
    plt.savefig("/eos/home-c/camendol/www/LaserTiming/blue_FEDs_sub/"+str(FED)+"_"+str(var)+".pdf")
    plt.savefig("/eos/home-c/camendol/www/LaserTiming/blue_FEDs_sub/"+str(FED)+"_"+str(var)+".png")
    trimmed.pivot_table(columns = "iphi", index = "ieta", values = var).to_csv("/eos/home-c/camendol/www/LaserTiming/blue_FEDs_sub/"+str(FED)+"_"+str(var)+".txt")









