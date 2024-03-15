import csv
import re
import os
import random # For testing purposes only

import networking

sensor_log_path = "logs/sensor_log_"

internal_temp = 20 # assume room temp
SCALE_INTERNAL_TEMP = True

sensor_offset = {}
sensor_units = {}

sensor_data_dict = {}

def initialize_sensor_info(sensor_list, config_name):

    csv_header_list = ['Timestamp (ms)']
    for sensor in sensor_list:
        sensor_offset[sensor['P and ID']] = 0
        sensor_units[sensor['P and ID']] = sensor["Unit"]
        csv_header_list.append(sensor["P and ID"] + "_raw")
        csv_header_list.append(sensor["P and ID"] + "_value")
        csv_header_list.append(sensor["P and ID"] + "_offset")
        sensor_data_dict[sensor['P and ID']] = None

    # initialize sensor_log
    global sensor_log_path

    filenames = sorted(list(filter(lambda flname: "sensor_log" in flname, next(os.walk("logs"), (None, None, []))[2])), key=file_num_from_name)
    try:
        current_filenum = int(re.findall('\d+', filenames[-1])[0]) + 1
    except: 
        current_filenum = 0 

    sensor_log_path = "logs/sensor_log_" + str(current_filenum) + "_" + config_name + ".csv"
    with open(sensor_log_path, "w") as file:
        csv.writer(file).writerow(csv_header_list)
        file.flush()
        file.close()

def file_num_from_name(fname):
    return int(re.findall('\d+', fname)[0]) + 1

def get_sensor_data():
    global sensor_data_dict
    most_recent_data_packet = networking.get_sensor_data()
    for data in most_recent_data_packet:
        sensor_data_dict[data] = most_recent_data_packet[data]
    processed_data_dict = {}
    for sensor in sensor_data_dict:
        if sensor_data_dict[sensor]:
            processed_data_dict[sensor] = sensor_data_dict[sensor] - sensor_offset[sensor]
    return processed_data_dict


def tare(sensorID):
    sensor_offset[sensorID] = sensor_data_dict[sensorID]


def untare(sensorID):
    sensor_offset[sensorID] = 0

def process_sensor_dict(sensor_data_dict):
    processed_dict = {}
    global internal_temp

    for sensor in sensor_data_dict:
        raw_value = sensor_data_dict[sensor] - sensor_offset[sensor]
        val_in_volts = raw_value / 1000.0

        match sensor_units[sensor]:
            case "PSI_S1k":
                raw_value = 250 * val_in_volts - 125
            case "PSI_H5k":
                raw_value = 1250 * 2 * val_in_volts - 625
            case "PSI_M1k":
                raw_value = (1000.0 * val_in_volts)/(0.100 * 128)
            case "PSI_M5k":
                raw_value = (5000.0 * val_in_volts)/(0.100 * 128)
            case "Degrees C":
                raw_value = (195.8363374*val_in_volts + 5.4986782) + internal_temp
            case "Volts":
                raw_value = val_in_volts
            case "C Internal":
                internal_temp = raw_value/1000 if SCALE_INTERNAL_TEMP else raw_value
            case "lbs_tank":
                raw_value = val_in_volts*1014.54 - 32.5314
            case "lbs_engine":
                raw_value = (-val_in_volts*5128.21 - 11.2821)/2
            case "alt_ft":
                raw_value = raw_value * 3.281 #m to ft. Dammit Kamer!
            case "g_force":
                raw_value = raw_value * 0.00102 # cm/s^2 to G
            case _ :
                pass
                #print("Unexpected Unit")
        
        processed_dict[sensor] = raw_value

    return processed_dict


def log_sensor_data(timestamp, sensor_data_dict):

    unit_converted_data = process_sensor_dict(sensor_data_dict)
    data_to_log = [timestamp]

    for sensor in sensor_offset:
        try:
            data_to_log.extend([sensor_data_dict[sensor], unit_converted_data[sensor], sensor_offset[sensor]])
        except: 
            data_to_log.extend([None, None, None])

    with open(sensor_log_path, "a") as file:
        csv.writer(file).writerow(data_to_log)
        file.flush()
        file.close()

def get_dummy_sensor_data():
    dummy_data_dict = {}
    for sensor in sensor_offset:
        dummy_data_dict[sensor] = random.random()*100
    return dummy_data_dict