# part of the python standard library
from threading import Lock
import json
import os
import time
import webbrowser
import sys

# Define the path to the custom library directory and import the custom libs
# if there are yellow error squiggles under some import stuff ignore it
custom_libs_path = os.path.abspath("./libs")
sys.path.insert(0, custom_libs_path)
from flask import Flask, render_template
from flask_socketio import SocketIO

# import other project files
import configuration
import networking
import autoseq
import sensor
import actuator

# Socket IO config
async_mode = None

# could use used to make unique id's for webpages
sessionID = str(time.time()).split('.')[0]
print("sessionID", sessionID)


start_time = time.time()

# GLOBAL VARIABLES for sensors and actuators
actuator_list = []
sensor_list = []

mote_status = []
config_file_name = None

# Global Variable that determines if stand is armed
armed = False

app = Flask(__name__, static_url_path='/static')
socketio = SocketIO(app, async_mode=async_mode)

# Threads 
sensor_thread = None
sensor_thread_lock = Lock()
connection_thread = None
connection_thread_lock = Lock()

#i am in webthocket hell
#lmao skill issue


# flask routes for webpages
@app.route('/' + sessionID, methods=['GET']) # + sessionID here if needed
def index():
    return render_template('index.html', armed=armed, config_file_name = config_file_name, sensor_list=sensor_list, actuator_list=actuator_list, sessionID=sessionID)

@app.route('/autosequence' + sessionID, methods=['GET'])
def autosequence():
    return render_template('autosequence.html', autosequence_commands=autoseq.autosequence_commands, abort_sequence_commands= autoseq.abort_sequence_commands, time_to_show=autoseq.time_to_show, autosequence_file_name = autoseq.autosequence_file_name, abort_sequence_file_name = autoseq.abort_sequence_file_name, redline_file_name = autoseq.redline_file_name, redline_states = autoseq.redline_states, armed = armed, redline_on = autoseq.redline_on)

@app.route('/pidview' + sessionID, methods=['GET'])
def pidview():
    return render_template('pidview.html', actuator_list=actuator_list, sensor_list=sensor_list, actuator_states_and_sensor_tare_states=actuator.actuator_states)

@app.route('/sensors' + sessionID, methods=['GET'])
def sensors():
    return render_template('sensors.html', sensor_list=sensor_list, armed = armed)

@app.route('/actuators' + sessionID, methods=['GET'])
def actuators():
    return render_template('actuators.html', actuator_list=actuator_list, actuator_states=actuator.actuator_states, actuator_acks = actuator.actuator_acks, armed = armed)


# methods to listen for client events
@socketio.on('uploadConfigFile')
def loadConfigFile(CSVFileAndFileContents, fileName):
    global config_file_name
    config_file_name = fileName

    CSVFile = CSVFileAndFileContents[0]
    fileContents = CSVFileAndFileContents[1]

    if CSVFile == 'csvFile1':
        global sensor_list
        global actuator_list

        try:
            actuator_list, sensor_list = configuration.load_config(fileContents)
            socketio.emit('sensor_and_actuator_config_uploaded')
        except:
            socketio.emit("config_file_header_error")
        
        sensor.initialize_sensor_info(sensor_list, config_file_name)
        actuator.initialize_actuator_states(actuator_list, config_file_name)
        autoseq.initialize_sensors_and_actuators(sensor_list, actuator_list)
            

@socketio.on('connect_request')
def handle_connect_request():
    print("Attempting to send config to MoTE")
    networking.send_config_to_mote(sensor_list, actuator_list) # Networking function

@socketio.on('armOrDisarmRequest')
def armDisarm():
    global armed
    if armed:
        armed = False
    elif not armed:
        armed = True
    else:
        print('client requested a non-boolean state')
    socketio.emit('armOrDisarmResponse', armed)
    print('variable armed is now: ', armed)

@socketio.on('actuator_button_press')
def handle_button_press(buttonID, state, current_time):
    state_bool = True if state == "On" else False if state == "Off" else None
    buttonDict = [config_line for config_line in actuator_list if config_line['P and ID'] == buttonID][0]

    if state_bool is None:
        print(f"Invalid state {state}, no command sent")
        return

    print('received button press: ', buttonID, state, 'Delay:',(time.time_ns() // 1_000_000) - current_time)
    if armed:
        networking.send_actuator_command(buttonDict['Mote id'], buttonDict['Pin'], state_bool, buttonDict['Interface Type'], buttonID=buttonID)
    else:
        print("stand is disarmed!!! " + buttonID + " was not set to " + state)

@socketio.on('actuator_button_coordinates')
def actuator_button_coordinates(get_request_or_coordinate_data):
    # if pidview.html is requesting the coordinates stored in the .json
    if get_request_or_coordinate_data == 'getCoordinates':
        #emit coordinates'test': 'testval'
        with open(os.path.dirname(os.path.abspath(__file__)) + '/static/coordinates.json', 'r') as file:
            coordinates = json.load(file)
            print("pidview.html is requesting coordinates from .json")
        socketio.emit('get_actuator_button_location_config', coordinates)
    else: # pidview.html is sending new button coordinates for saving
        with open(os.path.dirname(os.path.abspath(__file__)) + '/static/coordinates.json', 'w') as file:
            json.dump(get_request_or_coordinate_data, file)
            print("button coordinates saved to .json file")


@socketio.on('autosequenceFile_uploaded')
def handle_autoseqeunce(file, fileName):
    global time_to_show
    message = autoseq.parse_and_check_sequence_files('autosequence', fileName, file)
    time_to_show = int(int(autoseq.autosequence_commands[0]['Time(ms)'])/1000)
    socketio.emit(message)
    #print("an autosequence file error occured")


@socketio.on('abortSequenceFile_uploaded')
def handle_abort_sequence(file, fileName):
    message = autoseq.parse_and_check_sequence_files('abort_sequence', fileName, file)
    socketio.emit(message)

@socketio.on('redlineFile_uploaded')
def handle_redline(file, fileName):
    message = autoseq.parse_and_check_redline(file, fileName)
    socketio.emit(message)

@socketio.on('redline_toggle')
def handle_redline_toggle(bool):
    autoseq.redline_on = bool

@socketio.on('launch_request')
def handle_launch_request():
    if autoseq.autosequence_occuring:
        return None
    elif not autoseq.autosequence_commands:
        socketio.emit('no_autosequence')
        return None
    elif not autoseq.abort_sequence_commands:
        socketio.emit('no_abort_sequence')
    elif armed == False:
        socketio.emit('stand_disarmed')
    else:
        socketio.emit('autosequence_started')
        autoseq.autosequence_occuring = True
        autoseq.autosequence_cancel = False
        autoseq.time_to_show = int(int(autoseq.autosequence_commands[0]['Time(ms)'])/1000)
        execute_sequence(autoseq.autosequence_commands, 'autosequence')
        autoseq.autosequence_occuring = False

timer_lock = False

@socketio.on('start_timer')
def broadcast_time():
    socketio.emit('start_timer_ack')
    global timer_lock

    if timer_lock:
        return None
    timer_lock = True

    print('timer started')
    while True:
        timeAtBeginning = time.perf_counter()
        socketio.emit('current_time', autoseq.time_to_show)
        while (time.perf_counter() - timeAtBeginning) < 1:
            if autoseq.autosequence_cancel or not autoseq.autosequence_occuring:
                print("timer stopped, thread ended")
                timer_lock = False
                return None
            socketio.sleep(.01)
        autoseq.time_to_show += 1


@socketio.on('abort_request')
def handle_abort_request():
    print("Received abort request")
    if (autoseq.autosequence_occuring):
        autoseq.autosequence_occuring = False
        autoseq.autosequence_cancel = True
        execute_sequence(autoseq.abort_sequence_commands, 'abort_sequence')
    else:
        socketio.emit('no_autosequence_running')

@socketio.on('cancel_request')
def handle_cancel_request():
    print("Received cancel request at",autoseq.time_to_show,"seconds")
    if (autoseq.autosequence_occuring):
        autoseq.autosequence_cancel = True
    else:
        socketio.emit('no_autosequence_running')

@socketio.on('tare')
def handle_tare(sensorID, bool):
    if bool: 
        sensor.tare(sensorID)
    else:
        sensor.untare(sensorID)
    

# Home page functions
def update_connection_status():
    print("started connection status thread")
    global mote_status
    global start_time
    while True:
        mote_status = networking.get_mote_status()
        socketio.emit('mote_status_and_system_time', (mote_status, time.time()- start_time))
        socketio.sleep(1)


# Autosequence page functions 
def execute_sequence(commands, sequenceName):
    for command in commands:
        timeAtBeginning = time.perf_counter()
        stringState = 'on' if command['State'] == True else 'off' # on/off state used in webpages
        socketio.emit('responding_with_button_data', [command['P and ID'], stringState])
        command['Completed'] = True

        socketio.emit(sequenceName + '_command_sent', command)

        command_bool = True if command['State'].lower() == 'true' else False
        # send actuator to mote #
        if command['Type'] == 'Actuator' :
            buttonDict = [config_line for config_line in actuator_list if config_line['P and ID'] == command['P and ID']][0]
            networking.send_actuator_command(buttonDict['Mote id'], buttonDict['Pin'], command_bool, buttonDict['Interface Type'], buttonDict['P and ID'])
        
        while (time.perf_counter() - timeAtBeginning) < command['Sleep time(ms)']/1000:
            if sequenceName == 'autosequence' and (autoseq.autosequence_cancel or not autoseq.autosequence_occuring):
                autoseq.autosequence_occuring = False
                print("Launch cancelled")
                return None
            time.sleep(.001)

# Sensor and actuator acks page functions
def sensor_data_and_actuator_acks_thread():
    print("started sensor data thread")
    socketio.sleep(1)
    while True:
        socketio.sleep(1/20)
        sensors_and_data = sensor.get_sensor_data()
        autoseq.redline_check(sensors_and_data)
        actuator_data = (actuator.get_actuator_states(), actuator.get_actuator_acks())
        #timestamp = time.time_ns() // 1000000
        socketio.emit('sensor_data', sensors_and_data)
        socketio.emit('update_actuator_data', actuator_data)


# start all background threads
networking.start_telemetry_thread()

with sensor_thread_lock:
    if sensor_thread is None:
        sensor_thread = socketio.start_background_task(sensor_data_and_actuator_acks_thread)

with connection_thread_lock:
    if connection_thread is None:
        connection_thread = socketio.start_background_task(update_connection_status)


# open the GUI interface (this is the last thing that runs besides functions)
webbrowser.open_new('http://127.0.0.1:5001/' + sessionID) # + sessionID here if needed


# start the app (this is the first thing that runs)
if __name__ == '__main__':
    socketio.run(app, port=5001, debug=False)
