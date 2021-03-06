'''
Perform Graph-based Depth Correction (GDC)
in batch over KITTI object dataset.

Author: Yurong You
Date: Feb 2020
'''

import argparse
import os
import os.path as osp
import time
from multiprocessing import Pool, Process, Queue

import sys
import traceback
import multiprocessing

import numpy as np
from tqdm.auto import tqdm

from data_utils.kitti_util import Calibration
from gdc import GDC

import signal

def sig_handler(signum, frame):
    print("segfault")
    print("signum", signum)
    print("frame", frame)
    exit()

signal.signal(signal.SIGSEGV, sig_handler)
os.kill(os.getpid(), signal.SIGSEGV)

parser = argparse.ArgumentParser(description='GDC in batch')
parser.add_argument('--input_path', type=str,
                    help='path to predicted depthmap')
parser.add_argument('--calib_path', type=str,
                    help='path to calibration files')
parser.add_argument('--gt_depthmap_path', type=str,
                    help='path to groundtruth depthmap')
parser.add_argument('--output_path', type=str)
parser.add_argument('--split_file', type=str, required=True,
                    help='indices of scene to be corrected')
parser.add_argument('--k', type=int, default=10, help="k for KNN")
parser.add_argument('--recon_tol', type=float, default=5e-4, help="recon_tol for GDC")
parser.add_argument('--method', type=str, default='cg',
                    help='cg or gmres')
parser.add_argument('--disable_subsample', dest="subsample", action='store_false',
                    help='whether subsampling points')
parser.add_argument('--consider_range', type=float, nargs='+', default=[-0.1, 3.0],
                    help='consider_range')
parser.add_argument('--threads', type=int, default=4)


def GDC_and_save(func, save_path, *args, **kwds):
    # print("GDC_and_save")
    try:
        corrected = func(*args, **kwds)
        np.save(save_path, corrected.astype(np.float32))
    except Exception as error:
        raise Exception("".join(traceback.format_exception(*sys.exc_info())))


def main(args):
    if not osp.isdir(args.output_path):
        os.makedirs(args.output_path)

    with open(args.split_file) as f:
        idx_list = [int(x.strip()) for x in f.readlines() if len(x.strip()) > 0]

    if args.threads <= 1:
        print("Starting in single thread mode")
        for idx in tqdm(idx_list):
            save_path = osp.join(args.output_path, "{:06d}".format(idx))
            if osp.exists(save_path + '.npy'):
                continue
            predict = np.load(
                osp.join(args.input_path, "{:06d}.npy".format(idx)))
            gt = np.load(osp.join(args.gt_depthmap_path,
                                  "{:06d}.npy".format(idx)))
            calib = Calibration(
                osp.join(args.calib_path, "{:06d}.txt".format(idx)))

            GDC_and_save(GDC, save_path, predict, gt, calib,
                          W_tol=3e-5, recon_tol=args.recon_tol,
                        k=args.k, method=args.method, subsample=args.subsample)
    else:
        # multiprocessing
        pool = Pool(args.threads)
        res = []
        pbar = tqdm(total=len(idx_list))
        def update(*a):
            pbar.update()

        for idx in idx_list:
            predict = np.load(osp.join(args.input_path, "{:06d}.npy".format(idx)))
            gt = np.load(osp.join(args.gt_depthmap_path, "{:06d}.npy".format(idx)))
            calib = Calibration(osp.join(args.calib_path, "{:06d}.txt".format(idx)))
            save_path = osp.join(args.output_path, "{:06d}".format(idx))
            res.append((idx, pool.apply_async(
                GDC_and_save, args=(GDC, save_path, predict, gt, calib),
                kwds={'W_tol': 1e-5, 'recon_tol': args.recon_tol, 'k': args.k,
                    'method': args.method, 'subsample': args.subsample, 'consider_range': args.consider_range, 'verbose': True}, callback=update)))

        pool.close()
        pool.join()
        pbar.clear(nolock=False)
        pbar.close()
        for idx, r in res:
            if not r.successful():
                print(idx, r.get())

if __name__ == '__main__':
    args = parser.parse_args()
    main(args)
