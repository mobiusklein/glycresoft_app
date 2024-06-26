import os
from typing import Any

from glycresoft_app.project import sample
from .task_process import Task, Message


from glycresoft.cli.validators import (
    validate_sample_run_name,
    validate_database_unlocked)
from ms_deisotope.tools.utils import validate_averagine

import ms_deisotope
import ms_peak_picker

from ms_deisotope import MSFileLoader
from ms_deisotope.data_source import RandomAccessScanSource, Scan
from ms_deisotope.output import ProcessedMSFileLoader

from glycresoft.profiler import SampleConsumer
from glycresoft.serialize import SampleRun
from glycresoft.scan_cache import ThreadedMzMLScanStorageHandler

import logging
logger = logging.getLogger(__name__)


def preprocess(mzml_file, database_connection, averagine=None, start_time=None, end_time=None,
               maximum_charge=None, name=None, msn_averagine=None, score_threshold=35.,
               msn_score_threshold=5., missed_peaks=1, msn_missed_peaks=1, n_processes=5, storage_path=None,
               extract_only_tandem_envelopes=False, ms1_background_reduction=5.,
               msn_background_reduction=0, ms1_averaging=0,
               channel=None, **kwargs):

    minimum_charge = 1 if maximum_charge > 0 else -1
    charge_range = (minimum_charge, maximum_charge)
    logger.info("Begin Scan Interpolation")
    loader: RandomAccessScanSource[Any, Scan] = MSFileLoader(mzml_file)
    if len(loader) == 0:
        channel.abort("Cannot process an empty MS data file")
    start_scan = loader.get_scan_by_time(start_time)
    if start_scan is None:
        start_scan = loader[0]

    if loader.has_ms1_scans() == False:
        extract_only_tandem_envelopes = False

    try:
        start_scan_id = loader._locate_ms1_scan(start_scan).id
    except IndexError:
        start_scan_id = start_scan.id

    end_scan = loader.get_scan_by_time(end_time)
    if end_scan is None:
        end_scan = loader[-1]
    logger.info("Processing from sample time %0.3f minutes to %0.3f minutes", start_scan.scan_time, end_scan.scan_time)
    try:
        end_scan_id = loader._locate_ms1_scan(end_scan).id
    except IndexError:
        end_scan_id = end_scan.id

    loader.reset()
    loader.make_iterator(grouped=True)

    first_batch = next(loader)
    if first_batch.precursor is not None:
        is_profile = first_batch.precursor.is_profile
    elif first_batch.products:
        is_profile = first_batch.products[0].is_profile
    if is_profile:
        logger.info("Spectra are profile")
    else:
        logger.info("Spectra are centroided")

    logger.info("Resolving Sample Name")
    if name is None:
        name = os.path.splitext(os.path.basename(mzml_file))[0]

    name = validate_sample_run_name(None, database_connection, name)

    logger.info("Validating arguments")
    try:
        averagine = validate_averagine(averagine)
    except Exception:
        channel.abort("Could not validate MS1 Averagine %s" % averagine)

    try:
        msn_averagine = validate_averagine(msn_averagine)
    except Exception:
        channel.abort("Could not validate MSn Averagine %s" % msn_averagine)

    if is_profile:
        ms1_peak_picking_args = {
            "transforms": [
                ms_peak_picker.scan_filter.FTICRBaselineRemoval(
                    scale=ms1_background_reduction, window_length=2.),
                ms_peak_picker.scan_filter.SavitskyGolayFilter()
            ],
            'signal_to_noise_threshold': 1.0,
        }
        if ms1_background_reduction == 0:
            ms1_peak_picking_args['transforms'] = []
    else:
        ms1_peak_picking_args = {
            "transforms": [
                ms_peak_picker.scan_filter.FTICRBaselineRemoval(
                    scale=ms1_background_reduction, window_length=2.),
            ]
        }
        if ms1_background_reduction == 0:
            ms1_peak_picking_args['transforms'] = []

    if msn_background_reduction > 0:
        msn_peak_picking_args = {
            "transforms": [
                ms_peak_picker.scan_filter.FTICRBaselineRemoval(
                    scale=msn_background_reduction, window_length=2.),
            ]
        }
    else:
        msn_peak_picking_args = {'transforms': []}

    ms1_deconvolution_args = {
        "scorer": ms_deisotope.scoring.PenalizedMSDeconVFitter(score_threshold, 2.),
        "averagine": averagine,
        "charge_range": charge_range,
        "max_missed_peaks": missed_peaks,
        "truncate_after": SampleConsumer.MS1_ISOTOPIC_PATTERN_WIDTH,
        "ignore_below": SampleConsumer.MS1_IGNORE_BELOW
    }

    msn_deconvolution_args = {
        "scorer": ms_deisotope.scoring.MSDeconVFitter(msn_score_threshold),
        "averagine": msn_averagine,
        "charge_range": charge_range,
        "max_missed_peaks": msn_missed_peaks,
        "truncate_after": SampleConsumer.MSN_ISOTOPIC_PATTERN_WIDTH,
        "ignore_below": SampleConsumer.MSN_IGNORE_BELOW
    }

    consumer = SampleConsumer(
        mzml_file,
        ms1_peak_picking_args=ms1_peak_picking_args,
        ms1_deconvolution_args=ms1_deconvolution_args,
        msn_peak_picking_args=msn_peak_picking_args,
        msn_deconvolution_args=msn_deconvolution_args,
        storage_path=storage_path,
        sample_name=name,
        start_scan_id=start_scan_id,
        end_scan_id=end_scan_id,
        n_processes=n_processes,
        extract_only_tandem_envelopes=extract_only_tandem_envelopes,
        ms1_averaging=ms1_averaging,
        storage_type=ThreadedMzMLScanStorageHandler)

    try:
        consumer.start()
        logger.info("Updating New Sample Run")
        reader = ProcessedMSFileLoader(storage_path, use_index=False)
        reader.read_index_file()
        sample_run_data = reader.sample_run
        if reader.extended_index.msn_ids:
            sample_type = "MS/MS Sample"
        else:
            sample_type = "MS Sample"
        sample_run = sample.SampleRunRecord(
            name=sample_run_data.name,
            uuid=sample_run_data.uuid,
            completed=True,
            path=storage_path,
            sample_type=sample_type,
            user_id=channel.user.id)
        channel.send(Message(sample_run.to_json(), "new-sample-run"))
    except Exception:
        channel.send(Message.traceback())
        channel.abort("An error occurred during preprocessing.")


class PreprocessMSTask(Task):
    def __init__(self, mzml_file, database_connection, averagine, start_time, end_time, maximum_charge,
                 name, msn_averagine, score_threshold, msn_score_threshold, missed_peaks, msn_missed_peaks,
                 n_processes, storage_path, extract_only_tandem_envelopes, ms1_background_reduction,
                 msn_background_reduction, ms1_averaging,
                 callback, **kwargs):
        args = (mzml_file, database_connection, averagine, start_time, end_time, maximum_charge,
                name, msn_averagine, score_threshold, msn_score_threshold, missed_peaks, msn_missed_peaks,
                n_processes, storage_path, extract_only_tandem_envelopes, ms1_background_reduction,
                msn_background_reduction, ms1_averaging
                )
        job_name = "Preprocess MS %s" % (name,)
        kwargs.setdefault('name', job_name)
        Task.__init__(self, preprocess, args, callback, **kwargs)
