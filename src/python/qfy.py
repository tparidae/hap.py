#!/illumina/development/haplocompare/hc-virtualenv/bin/python
# coding=utf-8
#
# Copyright (c) 2010-2015 Illumina, Inc.
# All rights reserved.
#
# This file is distributed under the simplified BSD license.
# The full text can be found here (and in LICENSE.txt in the root folder of
# this distribution):
#
# https://github.com/Illumina/licenses/blob/master/Simplified-BSD-License.txt
#
# 9/9/2014
#
# Diploid VCF File Comparison
#
# Usage:
#
# For usage instructions run with option --help
#
# Author:
#
# Peter Krusche <pkrusche@illumina.com>
#

import sys
import os
import argparse
import logging
import traceback
import multiprocessing
import pandas
import json
import pyximport

pyximport.install()

scriptDir = os.path.abspath(os.path.dirname(__file__))
sys.path.append(os.path.abspath(os.path.join(scriptDir, '..', 'lib', 'python27')))

import Tools
from Tools.metric import makeMetricsObject, dataframeToMetricsTable
import Haplo.quantify
import Haplo.happyroc


def quantify(args):
    """ Run quantify and write tables """
    vcf_name = args.in_vcf[0]

    if not vcf_name or not os.path.exists(vcf_name):
        raise Exception("Cannot read input VCF.")

    logging.info("Counting variants...")

    output_vcf = args.reports_prefix + ".vcf.gz"
    roc_table = args.reports_prefix + ".roc.tsv"

    qfyregions = {}

    if args.fp_bedfile:
        if not os.path.exists(args.fp_bedfile):
            raise Exception("FP / Confident region file not found at %s" % args.fp_bedfile)
        qfyregions["CONF"] = args.fp_bedfile

    if args.strat_tsv:
        with open(args.strat_tsv) as sf:
            for l in sf:
                n, _, f = l.strip().partition("\t")
                if n in qfyregions:
                    raise Exception("Duplicate stratification region ID: %s" % n)
                if not os.path.exists(f):
                    f = os.path.join(os.path.abspath(os.path.dirname(args.strat_tsv)), f)
                if not os.path.exists(f):
                    raise Exception("Quantification region file %s not found" % f)
                qfyregions[n] = f

    if vcf_name == output_vcf or vcf_name == output_vcf + ".vcf.gz":
        raise Exception("Cannot overwrite input VCF: %s would overwritten with output name %s." % (vcf_name, output_vcf))

    Haplo.quantify.run_quantify(vcf_name,
                                roc_table,
                                output_vcf if args.write_vcf else False,
                                qfyregions,
                                args.ref,
                                threads=args.threads,
                                output_vtc=args.output_vtc,
                                output_rocs=args.do_roc,
                                qtype=args.type,
                                roc_val=args.roc,
                                roc_filter=args.roc_filter,
                                roc_delta=args.roc_delta,
                                clean_info=not args.preserve_info,
                                strat_fixchr=args.strat_fixchr)

    metrics_output = makeMetricsObject("%s.comparison" % args.runner)

    res = Haplo.happyroc.roc(roc_table, args.reports_prefix + ".roc")
    df = res["all"]

    # only use summary numbers
    df = df[(df["QQ"] == "*") & (df["Subset"] == "*") & (df["Filter"].isin(["ALL", "PASS"]))]

    summary_columns = ["Type",
                       "Filter",
                       "TRUTH.TOTAL",
                       "TRUTH.TP",
                       "TRUTH.FN",
                       "QUERY.TOTAL",
                       "QUERY.FP",
                       "QUERY.UNK",
                       "METRIC.Recall",
                       "METRIC.Precision",
                       "METRIC.Frac_NA"]

    for additional_column in ["TRUTH.TOTAL.TiTv_ratio",
                              "QUERY.TOTAL.TiTv_ratio",
                              "TRUTH.TOTAL.het_hom_ratio",
                              "QUERY.TOTAL.het_hom_ratio"]:
        summary_columns.append(additional_column)

    # Remove subtype
    summary_df = df[(df["Subtype"] == "*") & (df["Genotype"] == "*")]

    summary_df[summary_columns].to_csv(args.reports_prefix + ".summary.csv")

    metrics_output["metrics"].append(dataframeToMetricsTable("summary.metrics",
                                                             summary_df[summary_columns]))

    if args.write_counts:
        df.to_csv(args.reports_prefix + ".extended.csv")
        metrics_output["metrics"].append(dataframeToMetricsTable("all.metrics", df))

    essential_numbers = summary_df[summary_columns]

    pandas.set_option('display.max_columns', 500)
    pandas.set_option('display.width', 1000)

    essential_numbers = essential_numbers[essential_numbers["Type"].isin(
        ["SNP", "INDEL"])]

    logging.info("\n" + str(essential_numbers))

    # in default mode, print result summary to stdout
    if not args.quiet and not args.verbose:
        print "Benchmarking Summary:"
        print str(essential_numbers)

    # keep this for verbose output
    if not args.verbose:
        try:
            os.unlink(roc_table)
        except:
            pass

    for t in res.iterkeys():
        metrics_output["metrics"].append(dataframeToMetricsTable("roc." + t, res[t]))

    with open(args.reports_prefix + ".metrics.json", "w") as fp:
        json.dump(metrics_output, fp)


def updateArgs(parser):
    """ add common quantification args """
    parser.add_argument("-t", "--type", dest="type", choices=["xcmp", "ga4gh"],
                        help="Annotation format in input VCF file.")

    parser.add_argument("-f", "--false-positives", dest="fp_bedfile",
                        default=None, type=str,
                        help="False positive / confident call regions (.bed or .bed.gz).")

    parser.add_argument("--stratification", dest="strat_tsv",
                        default=None, type=str,
                        help="Stratification file list (TSV format -- first column is region name, second column is file name).")

    parser.add_argument("--stratification-fixchr", dest="strat_fixchr",
                        default=None, action="store_true",
                        help="Add chr prefix to stratification files if necessary")

    parser.add_argument("-V", "--write-vcf", dest="write_vcf",
                        default=False, action="store_true",
                        help="Write an annotated VCF.")

    parser.add_argument("-X", "--write-counts", dest="write_counts",
                        default=True, action="store_true",
                        help="Write advanced counts and metrics.")

    parser.add_argument("--no-write-counts", dest="write_counts",
                        default=True, action="store_false",
                        help="Do not write advanced counts and metrics.")

    parser.add_argument("--output-vtc", dest="output_vtc",
                        default=False, action="store_true",
                        help="Write VTC field in the final VCF which gives the counts each position has contributed to.")

    parser.add_argument("--preserve-info", dest="preserve_info", action="store_true", default=False,
                        help="When using XCMP, preserve and merge the INFO fields in truth and query. Useful for ROC computation.")

    parser.add_argument("--roc", dest="roc", default="QUAL",
                        help="Select a feature to produce a ROC on (INFO feature, QUAL, Q_GQ, ...).")

    parser.add_argument("--no-roc", dest="do_roc", default=True, action="store_false",
                        help="Disable ROC computation and only output summary statistics for more concise output.")

    parser.add_argument("--roc-filter", dest="roc_filter", default=False,
                        help="Select a filter to ignore when making ROCs.")

    parser.add_argument("--roc-delta", dest="roc_delta", default=1, type=float,
                        help="Minimum spacing between ROC QQ levels.")


def main():
    parser = argparse.ArgumentParser("Quantify annotated VCFs")

    parser.add_argument("-v", "--version", dest="version", action="store_true",
                        help="Show version number and exit.")

    parser.add_argument("in_vcf", help="VCF file to quantify", nargs=1)

    updateArgs(parser)

    # generic, keep in sync with hap.py!
    parser.add_argument("-o", "--report-prefix", dest="reports_prefix",
                        default=None,
                        help="Filename prefix for report output.")

    parser.add_argument("-r", "--reference", dest="ref", default=None, help="Specify a reference file.")

    parser.add_argument("--threads", dest="threads",
                        default=multiprocessing.cpu_count(), type=int,
                        help="Number of threads to use.")

    parser.add_argument("--logfile", dest="logfile", default=None,
                        help="Write logging information into file rather than to stderr")

    verbosity_options = parser.add_mutually_exclusive_group(required=False)

    verbosity_options.add_argument("--verbose", dest="verbose", default=False, action="store_true",
                                   help="Raise logging level from warning to info.")

    verbosity_options.add_argument("--quiet", dest="quiet", default=False, action="store_true",
                                   help="Set logging level to output errors only.")

    args, unknown_args = parser.parse_known_args()

    args.runner = "qfy.py"

    if not args.ref:
        args.ref = Tools.defaultReference()

    if args.verbose:
        loglevel = logging.INFO
    elif args.quiet:
        loglevel = logging.ERROR
    else:
        loglevel = logging.WARNING

    # reinitialize logging
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    logging.basicConfig(filename=args.logfile,
                        format='%(asctime)s %(levelname)-8s %(message)s',
                        level=loglevel)

    # remove some safe unknown args
    unknown_args = [x for x in unknown_args if x not in ["--force-interactive"]]
    if len(sys.argv) < 2 or len(unknown_args) > 0:
        if unknown_args:
            logging.error("Unknown arguments specified : %s " % str(unknown_args))
        parser.print_help()
        exit(0)

    if args.version:
        print "qfy.py %s" % Tools.version
        exit(0)

    quantify(args)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.error(str(e))
        traceback.print_exc(file=Tools.LoggingWriter(logging.ERROR))
        exit(1)