"""
Allen Brain Observatory
=================================

Create an nwb file from Allen Brain Observatory data.
"""

########################################
# This example demostrates the basic functionality of several parts of the pynwb write API, centered around the optical physiology submodule (pynwb.ophys). We will use the allensdk as a read API, while leveraging the pynwb data model and write api to transform and write the data back to disk.

########################################
# .. image:: http://interactive.blockdiag.com/image?compression=deflate&encoding=base64&src=eJyVkFEKAjEMRP89RS_gCQSvUrLd2W6wTWrTIiLe3S0KwoIf_k2SN5OQKWm4zEzRPQ7OyW1aOMEdz84a5566DV0qDNKoscrpN9aQS6IG2zEUrp2Nh3uUtYuwRG8FmHcoioZ1748QVEpDamla1ruxJo330eFMcaRtmwUfhAMlH1YSQdpllaoBZpvjzW5ZPuvc39N5WTxLQ10o4C_nOAPeEPP3Uc8XlV14ZQ

import datetime

from allensdk.core.brain_observatory_cache import BrainObservatoryCache
import allensdk.brain_observatory.stimulus_info as si

from pynwb import NWBFile, NWBHDF5IO, TimeSeries
from pynwb.ophys import OpticalChannel, DfOverF, ImageSegmentation
from pynwb.image import ImageSeries, IndexSeries


# Settings:
ophys_experiment_id = 562095852
save_file_name = 'brain_observatory.nwb'

########################################
# Let's begin by downloading an Allen Institute Brain Observatory file.  After we cache this file locally (approx. 450 MB), we can open data assets we wish to write into our NWB:N file.  These include stimulus, acquisition, and processing data, as well as time "epochs" (intervals of interest)".
boc = BrainObservatoryCache(manifest_file='manifest.json')
dataset = boc.get_ophys_experiment_data(ophys_experiment_id)
metadata = dataset.get_metadata()
cell_specimen_ids = dataset.get_cell_specimen_ids()
timestamps, dFF = dataset.get_dff_traces()
stimulus_list = [s for s in si.SESSION_STIMULUS_MAP[metadata['session_type']]
                 if s is not 'spontaneous']
running_data, _ = dataset.get_running_speed()
trial_table = dataset.get_stimulus_table('master')
trial_table['start'] = timestamps[trial_table['start'].values]
trial_table['end'] = timestamps[trial_table['end'].values]
epoch_table = dataset.get_stimulus_epoch_table()
epoch_table['start'] = timestamps[epoch_table['start'].values]
epoch_table['end'] = timestamps[epoch_table['end'].values]

########################################
# First, lets create a top-level "file" container object.  All the other NWB:N data components will be stored hierarchically, relative to this container.  The data won't actually be written to the file system until the end of the script.

nwbfile = NWBFile(
    source='Allen Brain Observatory: Visual Coding',
    session_description='Allen Brain Observatory dataset',
    identifier=str(metadata['ophys_experiment_id']),
    session_start_time=metadata['session_start_time'],
    file_create_date=datetime.datetime.now()
)


########################################
# Next, we add stimuli templates (one for each type of stimulus), and a data series that indexes these templates to describe what stimulus was being shown during the experiment.
for stimulus in stimulus_list:
    visual_stimulus_images = ImageSeries(
        name=stimulus,
        source='NA',
        data=dataset.get_stimulus_template(stimulus),
        unit='NA',
        format='raw',
        timestamps=[0.0])
    image_index = IndexSeries(
        name=stimulus,
        source='NA',
        data=dataset.get_stimulus_table(stimulus).frame.values,
        unit='NA',
        indexed_timeseries=visual_stimulus_images,
        timestamps=timestamps[dataset.get_stimulus_table(stimulus).start.values])
    nwbfile.add_stimulus_template(visual_stimulus_images)
    nwbfile.add_stimulus(image_index)

########################################
# Besides the two-photon calcium image stack, the running speed of the animal was also recordered in this experiment.  We can store this data as a TimeSeries, in the acquisition portion of the file.

running_speed = TimeSeries(
    name='running_speed',
    source='Allen Brain Observatory: Visual Coding',
    data=running_data,
    timestamps=timestamps,
    unit='cm/s')

nwbfile.add_acquisition(running_speed)

########################################
# In NWB:N, an "epoch" is an interval of experiment time that can slice into a timeseries (for example running_speed, the one we just added).  PyNWB uses an object-oriented approach to create links into these timeseries, so that data is not copied multiple times.  Here, we extract the stimulus epochs (both fine and coarse-grained) from the Brain Observatory experiment using the allensdk.

for ri, row in trial_table.iterrows():
    nwbfile.create_epoch(start_time=row.start,
                         stop_time=row.end,
                         timeseries=[running_speed],
                         tags='trials',
                         description=str(ri))

for ri, row in epoch_table.iterrows():
    nwbfile.create_epoch(start_time=row.start,
                         stop_time=row.end,
                         timeseries=[running_speed],
                         tags='stimulus',
                         description=row.stimulus)

########################################
# In the brain observatory, a two-photon microscope is used to acquire images of the calcium activity of neurons expressing a flourescent protien indicator.  Essentially the microscope captures picture (30 times a second) at a single depth in the visual cortex (the imaging plane).  Let's use pynwb to store the metadata associated with this hardware and experimental setup:
optical_channel = OpticalChannel(
    name='optical_channel',
    source='Allen Brain Observatory: Visual Coding',
    description='2P Optical Channel',
    emission_lambda=520.,
)

imaging_plane = nwbfile.create_imaging_plane(
    name='imaging_plane',
    source='Allen Brain Observatory: Visual Coding',
    optical_channel=optical_channel,
    description='Imaging plane ',
    device=metadata['device'],
    excitation_lambda=float(metadata['excitation_lambda'].split(' ')[0]),
    imaging_rate='30.',
    indicator='GCaMP6f',
    location=metadata['targeted_structure'],
    manifold=[],
    conversion=1.0,
    unit='unknown',
    reference_frame='unknown',
)

########################################
#  The Allen Insitute does not include the raw imaging signal, as this data would make the file too large. Instead, these data are  preprocessed, and a dF/F flourescence signal extracted for each region-of-interest (ROI). To store the chain of computations necessary to describe this data processing pipeline, pynwb provides a "processing module" with interfaces that simplify and standarize the process of adding the steps in this provenance chain to the file:
ophys_module = nwbfile.create_processing_module(
    name='ophys_module',
    source='Allen Brain Observatory: Visual Coding',
    description='Processing module for 2P calcium responses',
)

########################################
# First, we add an image segmentation interface to the module.  This interface implements a pre-defined schema and API that facilitates writing segmentation masks for ROI's:

image_segmentation_interface = ImageSegmentation(
    name='image_segmentation',
    source='Allen Brain Observatory: Visual Coding')

ophys_module.add_data_interface(image_segmentation_interface)

plane_segmentation = image_segmentation_interface.create_plane_segmentation(
    name='plane_segmentation',
    source='NA',
    description='Segmentation for imaging plane',
    imaging_plane=imaging_plane)

for cell_specimen_id in cell_specimen_ids:
    curr_name = str(cell_specimen_id)
    curr_image_mask = dataset.get_roi_mask_array([cell_specimen_id])[0]
    plane_segmentation.add_roi(curr_name, [], curr_image_mask)

########################################
# Next, we add a dF/F  interface to the module.  This allows us to write the dF/F timeseries data associated with each ROI.

dff_interface = DfOverF(name='dff_interface', source='Flourescence data container')
ophys_module.add_data_interface(dff_interface)

rt_region = plane_segmentation.create_roi_table_region(
    description='segmented cells with cell_specimen_ids',
    names=[str(x) for x in cell_specimen_ids],
)

dFF_series = dff_interface.create_roi_response_series(
    name='df_over_f',
    source='NA',
    data=dFF,
    unit='NA',
    rois=rt_region,
    timestamps=timestamps,
)

########################################
# Now that we have created the data set, we can write the file to disk:
with NWBHDF5IO(save_file_name, mode='w') as io:
    io.write(nwbfile)

########################################
# For good measure, lets read the data back in and see if everything went as planned:
with NWBHDF5IO(save_file_name, mode='r') as io:
    nwbfile_in = io.read()