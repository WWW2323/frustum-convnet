""" Generic Code for Object Detection Evaluation

    Input:
    For each class:
        For each image:
            Predictions: box, score
            Groundtruths: box
    
    Output:
    For each class:
        precision-recal and average precision
    
    Author: Charles R. Qi
    Date: Oct 4th 2017
    
    Ref: https://raw.githubusercontent.com/rbgirshick/py-faster-rcnn/master/lib/datasets/voc_eval.py

Author: Charles R. Qi
Date: October, 2017
"""
import time
import numpy as np
import os
import sys
import matplotlib
import logging

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib as mpl

mpl.rc('axes', linewidth=2)

from utils.box_util import box3d_iou

from ops.pybind11 import box_ops_cc

logger = logging.getLogger(__name__)


def voc_ap(rec, prec, use_07_metric=False):
    """ ap = voc_ap(rec, prec, [use_07_metric])
    Compute VOC AP given precision and recall.
    If use_07_metric is true, uses the
    VOC 07 11 point method (default:False).
    """
    if use_07_metric:
        # 11 point metric
        ap = 0.
        for t in np.arange(0., 1.1, 0.1):
            if np.sum(rec >= t) == 0:
                p = 0
            else:
                p = np.max(prec[rec >= t])
            ap = ap + p / 11.
    else:
        # correct AP calculation
        # first append sentinel values at the end
        mrec = np.concatenate(([0.], rec, [1.]))
        mpre = np.concatenate(([0.], prec, [0.]))

        # compute the precision envelope
        for i in range(mpre.size - 1, 0, -1):
            mpre[i - 1] = np.maximum(mpre[i - 1], mpre[i])

        # to calculate area under PR curve, look for points
        # where X axis (recall) changes value
        i = np.where(mrec[1:] != mrec[:-1])[0]

        # and sum (\Delta recall) * prec
        ap = np.sum((mrec[i + 1] - mrec[i]) * mpre[i + 1])
    return ap


def get_iou(bb1, bb2):
    """ Compute IoU of two bounding boxes.
        ** Define your bod IoU function HERE **
    """

    iou3d, iou2d = box3d_iou(bb1, bb2)
    return iou3d


def get_iou_cc(bb1, bb2):
    ious = box_ops_cc.rbbox_iou_3d_pair(bb1[np.newaxis, ...], bb2[np.newaxis, ...])
    return ious[0, 1]


def eval_det_cls(pred, gt, ovthresh=0.25, use_07_metric=False):
    """ Generic functions to compute precision/recall for object detection
        for a single class.
        Input:
            pred: map of {img_id: [(bbox, score)]} where bbox is numpy array
            gt: map of {img_id: [bbox]}
            ovthresh: scalar, iou threshold
            use_07_metric: bool, if True use VOC07 11 point method
        Output:
            rec: numpy array of length nd
            prec: numpy array of length nd
            ap: scalar, average precision
    """

    # construct gt objects
    class_recs = {}  # {img_id: {'bbox': bbox list, 'det': matched list}}
    npos = 0
    for img_id in gt.keys():
        bbox = np.array(gt[img_id])
        det = [False] * len(bbox)
        npos += len(bbox)
        class_recs[img_id] = {'bbox': bbox, 'det': det}
    # pad empty list to all other imgids
    for img_id in pred.keys():
        if img_id not in gt:
            class_recs[img_id] = {'bbox': np.array([]), 'det': []}

    # construct dets
    image_ids = []
    confidence = []
    BB = []
    for img_id in pred.keys():
        for box, score in pred[img_id]:
            image_ids.append(img_id)
            confidence.append(score)
            BB.append(box)
    confidence = np.array(confidence)
    BB = np.array(BB)  # (nd,4 or 8,3)

    # sort by confidence
    sorted_ind = np.argsort(-confidence)
    sorted_scores = np.sort(-confidence)
    BB = BB[sorted_ind, ...]
    image_ids = [image_ids[x] for x in sorted_ind]

    # go down dets and mark TPs and FPs
    nd = len(image_ids)
    tp = np.zeros(nd)
    fp = np.zeros(nd)
    for d in range(nd):
        R = class_recs[image_ids[d]]
        bb = BB[d, :].astype(float)
        ovmax = -np.inf
        BBGT = R['bbox'].astype(float)

        if BBGT.size > 0:
            # compute overlaps
            for j in range(BBGT.shape[0]):
                iou = get_iou_cc(bb, BBGT[j])
                if iou > ovmax:
                    ovmax = iou
                    jmax = j

        if ovmax > ovthresh:
            if not R['det'][jmax]:
                tp[d] = 1.
                R['det'][jmax] = 1
            else:
                fp[d] = 1.
        else:
            fp[d] = 1.

    # compute precision recall
    fp = np.cumsum(fp)
    tp = np.cumsum(tp)
    rec = tp / float(npos)

    prec = tp / np.maximum(tp + fp, np.finfo(np.float64).eps)
    ap = voc_ap(rec, prec, use_07_metric)

    return rec, prec, ap


def eval_det(pred_all, gt_all, ovthresh=0.25, use_07_metric=False, result_dir=None):
    """ Generic functions to compute precision/recall for object detection
        for multiple classes.
        Input:
            pred_all: map of {img_id: [(classname, bbox, score)]}
            gt_all: map of {img_id: [(classname, bbox)]}
            ovthresh: scalar, iou threshold
            use_07_metric: bool, if true use VOC07 11 point method
        Output:
            rec: {classname: rec}
            prec: {classname: prec_all}
            ap: {classname: scalar}
    """
    # pred = {} # map {classname: pred}
    # gt = {} # map {classname: gt}
    # for img_id in pred_all.keys():
    #     for classname, bbox, score in pred_all[img_id]:
    #         if classname not in pred: pred[classname] = {}
    #         if img_id not in pred[classname]:
    #             pred[classname][img_id] = []
    #         if classname not in gt: gt[classname] = {}
    #         if img_id not in gt[classname]:
    #             gt[classname][img_id] = []
    #         pred[classname][img_id].append((bbox,score))
    # for img_id in gt_all.keys():
    #     for classname, bbox in gt_all[img_id]:
    #         if classname not in gt: gt[classname] = {}
    #         if img_id not in gt[classname]:
    #             gt[classname][img_id] = []
    #         gt[classname][img_id].append(bbox)

    rec = {}
    prec = {}
    ap = {}
    for classname in gt_all.keys():
        rec[classname], prec[classname], ap[classname] = eval_det_cls(
            pred_all[classname], gt_all[classname], ovthresh, use_07_metric)

    plot_folder = os.path.join(result_dir, 'ap_curves')
    if not os.path.exists(plot_folder):
        os.makedirs(plot_folder)

    for classname in sorted(ap.keys()):
        logging.info('%s: %.5f' % (classname, ap[classname]))
        # print('%s: %.5f' % (classname, ap[classname]))
        plt.plot(rec[classname], prec[classname], lw=3)
        fig = plt.gcf()
        fig.subplots_adjust(bottom=0.25)
        plt.xlim([0.0, 1.0])
        plt.ylim([0.0, 1.05])
        plt.xlabel('Recall', fontsize=24)
        plt.ylabel('Precision', fontsize=24)
        plt.title(classname, fontsize=24)
        # plt.show()
        plt.savefig(os.path.join(plot_folder, '%s.png' % classname))
        plt.cla()

    logging.info('mean_AP: %.5f' % (np.mean([ap[classname] for classname in ap])))
    # print('mean_AP: %.5f' % (np.mean([ap[classname] for classname in ap])))
    return rec, prec, ap