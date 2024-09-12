# Must call this script from the syn environment in slurm

# Open TensorStore datasets
import tensorstore as ts

from synful import synapse
import h5py
import os
from skimage import measure, segmentation
import logging
import pandas as pd
import numpy as np

NEUPRINT_APPLICATION_CREDENTIALS="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJlbWFpbCI6InNtMjY2N0BjYW0uYWMudWsiLCJsZXZlbCI6Im5vYXV0aCIsImltYWdlLXVybCI6Imh0dHBzOi8vbGgzLmdvb2dsZXVzZXJjb250ZW50LmNvbS9hL0FDZzhvY0p2WTBzQURieG1OMW11OFAySldsb2Q4U296alpaajc3c1NJbG5RdXk1bD1zOTYtYz9zej01MD9zej01MCIsImV4cCI6MTg3NTc0Mzc3N30.oyY1HURafdq3mZAr1TU82M1Lr2TpG4q2HRB42LcnZ90"
from neuprint import Client

c = Client('neuprint.janelia.org', dataset='hemibrain:v1.2.1', token=NEUPRINT_APPLICATION_CREDENTIALS)
c.fetch_version()


dataset_em = ts.open({
    'driver': 'neuroglancer_precomputed',
    'kvstore': 'gs://neuroglancer-janelia-flyem-hemibrain/emdata/raw/jpeg', # clahe_yz/jpeg
    'context': {'cache_pool': {'total_bytes_limit': 100_000_000}},
    'recheck_cached_data': 'open',
}).result()[ts.d['channel'][0]]

# when the synapses are on v1.0 is shown on neuroglancer, however we have checked with v1.2 the same neurons and locations to see if
# the same ids exist across version and whether they agree on locations
dataset_neuron = ts.open({
    'driver': 'neuroglancer_precomputed',
    'kvstore': 'gs://neuroglancer-janelia-flyem-hemibrain/v1.2/segmentation/',
    'context': {'cache_pool': {'total_bytes_limit': 100_000_000}},
    'recheck_cached_data': 'open',
}).result()[ts.d['channel'][0]]

print(f"EM Dataset: {dataset_em}")
print(f"Neuron Dataset: {dataset_neuron}")


# Function to write synapses into HDF5 format
def write_synapses_into_cremiformat(synapses, filename, offset=None, overwrite=False):
    logging.warning(
        "All orientations must be same, that is if coordinates are saved as XYZ, the EM vol should also be in XYZ")
    id_nr, ids, locations, partners, types = 0, [], [], [], []
    distances = []
    for syn in synapses:
        types.extend(['presynaptic_site', 'postsynaptic_site'])
        # ids.extend([np.array((syn.id_segm_pre, syn.id_segm_post))]) # we use original ids
        ids.extend([id_nr, id_nr + 1])  # generate ids
        # partners.extend([np.array((syn.id_segm_pre, syn.id_segm_post))]) # we use original ids
        partners.extend([np.array((id_nr, id_nr + 1))])  # generate ids

        assert syn.location_pre is not None and syn.location_post is not None
        locations.extend([np.array(syn.location_pre), np.array(syn.location_post)])
        id_nr += 2
        dist = np.linalg.norm(
            np.array(list(syn.location_pre), dtype=np.float32) - np.array(list(syn.location_post), dtype=np.float32))
        distances.append(dist)

    print('number of synapses in file {}'.format(len(synapses)))
    print('median {}, mean {}, max {}, min {}'.format(np.median(distances), np.mean(distances), np.max(distances),
                                                      np.min(distances)))

    if overwrite:
        h5_file = h5py.File(filename, 'w')
    else:
        h5_file = h5py.File(filename, 'a')

    dset = h5_file.create_dataset('annotations/ids', data=ids, compression='gzip')
    dset = h5_file.create_dataset('annotations/locations', data=np.stack(locations, axis=0).astype(np.float32),
                                  compression='gzip')
    dset = h5_file.create_dataset('annotations/presynaptic_site/partners',
                                  data=np.stack(partners, axis=0).astype(np.uint32), compression='gzip')
    dset = h5_file.create_dataset('annotations/types', data=np.array(types, dtype='S'), compression='gzip')

    if offset is not None:
        h5_file['annotations'].attrs['offset'] = offset
    h5_file.close()
    print('File written to {}'.format(filename))
    return distances


# Function to convert DataFrame to Synapse objects
def convert_to_synapses(df):
    synapses = []
    for _, row in df.iterrows():
    
        synapses.append(
            #synapse.Synapse(location_pre=(int(row['x_pre_roi']), int(row['y_pre_roi']), int(row['z_pre_roi'])),
            #                location_post=(int(row['x_post_roi']), int(row['y_post_roi']), int(row['z_post_roi'])),
            #                id_segm_pre=int(row['bodyId_pre']), id_segm_post=int(row['bodyId_post'])
            #                )
            synapse.Synapse(location_pre=(int(row['z_pre_roi']), int(row['y_pre_roi']), int(row['x_post_roi'])),
                            location_post=(int(row['z_post_roi']), int(row['y_post_roi']), int(row['x_post_roi'])),
                            id_segm_pre=int(row['bodyId_pre']), id_segm_post=int(row['bodyId_post'])
                            )
        )
    return synapses
    
def convert_to_pos_synapses(df):
    synapses = []
    for _, row in df.iterrows():
        pre_coords = (int(row['z_pre_roi']), int(row['y_pre_roi']), int(row['x_pre_roi']))
        post_coords = (int(row['z_post_roi']), int(row['y_post_roi']), int(row['x_post_roi']))
        
        # Check if any coordinate is negative
        if all(coord >= 0 for coord in pre_coords + post_coords):
            synapses.append(
                synapse.Synapse(location_pre=pre_coords,
                                location_post=post_coords,
                                id_segm_pre=int(row['bodyId_pre']),
                                id_segm_post=int(row['bodyId_post'])
                                )
            )
    return synapses


# Ensure all arrays have the same length
def check_lengths_and_convert_to_synapses(data_dict):
    lengths = [len(v) for v in data_dict.values()]
    if len(set(lengths)) != 1:
        print("Error: All arrays must be of the same length.")
        for key, value in data_dict.items():
            print(f"{key}: {len(value)}")
        raise ValueError("All arrays must be of the same length")

    df = pd.DataFrame(data_dict)
    return convert_to_pos_synapses(df) # convert_to_synapses may include negative coords


# Use the top 5 densely populated ROIs to create synapses and write to HDF5 files
totaldistances = []
overwrite = True

cluster_files = [
    "/cephfs/smohinta/catena/helpers/Cluster1_0.75/V1_CH0_prepost_points_0.75.csv",
    "/cephfs/smohinta/catena/helpers/Cluster1_0.75/V1_CH1_prepost_points_0.75.csv",
    "/cephfs/smohinta/catena/helpers/Cluster1_0.75/V1_CH2_prepost_points_0.75.csv",
    "/cephfs/smohinta/catena/helpers/Cluster1_0.75/V1_CH3_prepost_points_0.75.csv",
    "/cephfs/smohinta/catena/helpers/Cluster1_0.75/V1_CH4_prepost_points_0.75.csv"
]

top_roi_bboxes = pd.read_csv("/cephfs/smohinta/catena/helpers/V1_boundingboxes_corrected.csv")

for idx, roi in top_roi_bboxes.iterrows():
    x_min, x_max = roi['x_min'], roi['x_max']
    y_min, y_max = roi['y_min'], roi['y_max']
    z_min, z_max = roi['z_min'], roi['z_max']

    syn_inputs = pd.read_csv(cluster_files[idx])

    #em_vol = dataset_em[x_min:x_max, y_min:y_max, z_min:z_max].read().result()
    #neuron_vol = dataset_neuron[x_min:x_max, y_min:y_max, z_min:z_max].read().result()

    # print the neuron_ids that exist within this roi

    em_vol = np.transpose(dataset_em[x_min:x_max, y_min:y_max, z_min:z_max].read().result(), (2, 1, 0))  # zyx
    neuron_vol = np.transpose(dataset_neuron[x_min:x_max, y_min:y_max, z_min:z_max].read().result(), (2, 1, 0))  # zyx
    #np.unique(f" Unique ids in the cropped roi {neuron_vol}")
    
    # Relabel the segmentations
    # relabeled_neuron_vol, forward, backward = segmentation.relabel_sequential(neuron_vol)
    # print(f"relabeled meta data: \n forward: {forward}, backward: {backward}")

    synapse_data = {
        'bodyId_pre': syn_inputs['bodyId_pre'],
        'bodyId_post': syn_inputs['bodyId_post'],
        'x_pre_roi': (syn_inputs['x_pre'] - x_min).astype(int),
        'x_post_roi': (syn_inputs['x_post'] - x_min).astype(int),
        'y_pre_roi': (syn_inputs['y_pre'] - y_min).astype(int),
        'y_post_roi': (syn_inputs['y_post'] - y_min).astype(int),
        'z_pre_roi': (syn_inputs['z_pre'] - z_min).astype(int),
        'z_post_roi': (syn_inputs['z_post'] - z_min).astype(int)
    }

    print(synapse_data)

    # Check lengths and convert to Synapse objects
    synapses = check_lengths_and_convert_to_synapses(synapse_data)
    outputpath = f"./sylee_rois/cluster_075_unclahed_zyx/cutout{idx + 1}"  # change the path here based on brain region
    if not os.path.exists(outputpath):
        os.makedirs(outputpath)
    outputfile = f"{outputpath}/synapses_x{x_min}-{x_max}_y{y_min}-{y_max}_z{z_min}-{z_max}.hdf"  # './eb/cutout{}/synapses.hdf'.format(idx + 1)
    distances = write_synapses_into_cremiformat(synapses, outputfile, overwrite=overwrite)

    h5_file = h5py.File(outputfile, 'a')  # cannot be overwritten

    dset = h5_file.create_dataset('volumes/raw', data=em_vol, compression='gzip')
    dset = h5_file.create_dataset('volumes/labels/neuron_ids', data=neuron_vol.astype(np.uint64), compression='gzip')

    h5_file.close()

    totaldistances.extend(distances)
    print(f'ROI {idx + 1}: {len(synapses)} synapses written to {outputfile}')
