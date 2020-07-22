"""
    1. Select images
    2. Apply pre-processing corrections
        a. Limb-Brightening
        b. Inter-Instrument Transformation
    3. Coronal Hole Detection
    4. Convert to Map
    5. Combine Maps
    6. Save to DB
"""
sys.path.append("CHD")

import os
import datetime
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
# import scipy.interpolate as sp_interp
# import time
# import sunpy

from settings.app import App
import modules.DB_classes as db_class
from modules.DB_funs import init_db_conn, query_euv_images, add_map_dbase_record
import modules.datatypes as psi_d_types
from analysis.correct_images import correct_euv_images
from modules.map_manip import combine_maps
# import modules.coord_manip as coord
import modules.Plotting as EasyPlot
from helpers.misc_helpers import construct_map_path_and_fname
import helpers.psihdf as psihdf

# --- 1. Select Images -----------------------------------------------------
# INITIALIZE DATABASE CONNECTION
# DATABASE PATHS
raw_data_dir = App.RAW_DATA_HOME
hdf_data_dir = App.PROCESSED_DATA_HOME
database_dir = App.DATABASE_HOME
sqlite_filename = App.DATABASE_FNAME
# initialize database connection
use_db = "sqlite"
sqlite_path = os.path.join(database_dir, sqlite_filename)
db_session = init_db_conn(db_name=use_db, chd_base=db_class.Base, sqlite_path=sqlite_path)

# query some images
query_time_min = datetime.datetime(2011, 4, 1, 0, 0, 0)
query_time_max = datetime.datetime(2011, 5, 1, 0, 0, 0)
query_pd = query_euv_images(db_session=db_session, time_min=query_time_min, time_max=query_time_max)

# instruments
inst_list = ["AIA", "EUVI-A", "EUVI-B"]
# declare map and binning parameters
n_intensity_bins = 200
R0 = 1.01
del_mu = 0.2

# generate a dataframe to record methods
# methods_template is a combination of Meth_Defs and Var_Defs columns
meth_columns = []
for column in db_class.Meth_Defs.__table__.columns:
    meth_columns.append(column.key)
defs_columns = []
for column in db_class.Var_Defs.__table__.columns:
    defs_columns.append(column.key)
df_cols = set().union(meth_columns, defs_columns, ("var_val",))
methods_template = pd.DataFrame(data=None, columns=df_cols)
# generate a list of methods dataframes
methods_list = [methods_template] * query_pd.__len__()

# read hdf file(s) to a list of LOS objects
los_list = [None] * query_pd.__len__()
image_plot_list = [None] * query_pd.__len__()

# --- 2. Apply pre-processing corrections ------------------------------------------

corrected_images = correct_euv_images(db_session, query_time_min, query_time_max, query_pd,
                                      inst_list, hdf_data_dir, n_intensity_bins, R0)

# --- 3. Coronal Hole Detection ------------------------------------------------


# --- 4. Create maps -------------------------------------------------

# set save directory
map_data_dir = App.MAP_FILE_HOME

# map parameter definitions.
x_range = [0, 2 * np.pi]
y_range = [-1, 1]
map_nycoord = 1600
del_y = (y_range[1] - y_range[0]) / (map_nycoord - 1)
map_nxcoord = (np.floor((x_range[1] - x_range[0]) / del_y) + 1).astype(int)

# generate map x,y grids. y grid centered on equator, x referenced from lon=0
map_y = np.linspace(y_range[0], y_range[1], map_nycoord, dtype='<f4')
map_x = np.linspace(x_range[0], x_range[1], map_nxcoord, dtype='<f4')

map_list = [None] * len(los_list)
for ii in range(len(los_list)):
    # use fixed map resolution
    map_list[ii] = los_list[ii].interp_to_map(R0=R0, map_x=map_x, map_y=map_y, image_num=query_pd.image_id[ii])
    # Alternatively, we could have resolution determined from image
    # map_list[ii] = los_list[ii].interp_to_map(R0=R0)
    # record image info
    map_list[ii].append_image_info(query_pd.iloc[ii])

    # generate a record of the method and variable values used for interpolation
    new_method = {'meth_name': ("Im2Map_Lin_Interp_1",), 'meth_description':
        ["Use SciPy.RegularGridInterpolator() to linearly interpolate from an Image to a Map"] * 1,
                  'var_name': ("R0",), 'var_description': ("Solar radii",), 'var_val': (R0,)}
    # add to the methods dataframe for this map
    methods_list[ii] = methods_list[ii].append(pd.DataFrame(data=new_method), sort=False)

    # incorporate the methods dataframe into the map object
    map_list[ii].append_method_info(methods_list[ii])

    # simple plot
    EasyPlot.PlotMap(map_list[ii], nfig=10 + ii, title="Map " + str(ii))

    # save these maps to file and then push to the database
    # map_list[ii].write_to_file(map_data_dir, map_type='single', filename=None, db_session=db_session)

# --- 5. Combine maps -----------------------------------------------------
combined_map = combine_maps(map_list, del_mu=del_mu)

# generate a record of the method and variable values used for interpolation
new_method = {'meth_name': ("Min-Int-Merge_1",), 'meth_description':
    ["Minimum intensity merge version 1"] * 1,
              'var_name': ("del_mu",), 'var_description': ("max acceptable mu range",), 'var_val': (del_mu,)}
combined_map.append_method_info(pd.DataFrame(data=new_method))

EasyPlot.PlotMap(combined_map, nfig=2000, title="Minimum Intensity Merge Map")
plt.show()

combined_map.write_to_file(map_data_dir, map_type='synoptic', filename=None, db_session=db_session)

# --- 6. Save to DB -----------------------------------------------------------
# # add image info to map object
#
# # fname = gen_map_fname()
# fname = "/test/fname1.h5"
#
# time_of_compute = datetime.datetime.now()
# meth_name = "meth_101"
# # method is new to the DB. Add method definition before adding map
# new_method = True
# # in practice image_df will usually be the output of query_euv_images(), but here
# # we show that only the image_id column is needed for map record creation
# image_df = selected_images
# # variable values must be a DataFrame with columns var_name and var_val. These should
# # collected over steps 2-6 as necessary.
# var_vals = pd.DataFrame(data=[['x1', 1], ['x2', 10.1]], columns=["var_name", "var_val"])
#
# # --- generate a Map object ----------
# map_input = create_map_input_object(fname=fname, image_df=image_df, var_vals=var_vals, method_name=meth_name,
#                                     time_of_compute=time_of_compute)
#
# map_input.x = combined_map.x
# map_input.y = combined_map.y
# map_input.data = combined_map.data
# # send data to the DB
# db_session, map_id = add_map_dbase_record(db_session, psi_map=map_input)
