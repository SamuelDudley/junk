from pymavlink import mavutil
import time
import threading
import numpy as np
from bisect import bisect_left
import select

class State(object):
    def __init__(self, time_stamp, data):
        self.time_stamp = time_stamp
        self.data = data

class APSState(object):
    """holds the ap_state state"""
    def __init__(self):
        self.control_connection_in = mavutil.mavudp("127.0.0.1:14769")
        self.control_link_in = mavutil.mavlink.MAVLink(self.control_connection_in)
        self.control_connection_out = mavutil.mavudp("127.0.0.1:14779", input=False)
        self.control_link_out = mavutil.mavlink.MAVLink(self.control_connection_out)
        self.control_link_out.srcSystem = 122
        self.control_link_out.srcComponent = 3
        self.current_state = State(time_stamp=int((time.time()%1000)*100), data = {})
        self.state_history = []
        self.state_history_max_length = 1000 #samples
        
        self.alive = True

        
class AP_State(object):
    def __init__(self):
        self.state = APSState()
    
    
    def process_control_connection_in(self):
        state = self.state
        
        
        
        inputready,outputready,exceptready = select.select([state.control_connection_in.port],[],[])
        for s in inputready:

            msg = state.control_connection_in.recv_msg()
        
                
            if msg != None:
                msg_id = msg.get_msgId()
                msg_type = msg.get_type()
                msg_dict = msg.to_dict()
                
                if msg_type == 'GPS_RAW':
                    print msg_dict
    #             
                if (msg_type == 'ATTITUDE' or msg_type == 'GLOBAL_POSITION_INT' or msg_type == 'VFR_HUD'):
                    print msg_type
		    self.update_current_state(msg_dict)
                    self.log_current_state()
                    self.update_state_history()
    #                 
                    
                if (msg_type == 'COMMAND_LONG'):
                    print ''
                    print msg_dict['command'], msg_dict['param1']
                    if msg_dict['command'] == 122:
                        #its a state request
                        
                        state_entry = self.get_state_from_history(msg_dict['param1'])
			
			if not state_entry:
			    return False
                        
                        #inform the camera what image we are talking about
                        m = state.control_link_out.command_long_encode(122, 100, 122, 0, msg_dict['param1'], msg_dict['param2'], state_entry.time_stamp ,0,0,0,0 )
                        state.control_link_out.send(m)
                        
                        #make a GLOBAL_POSITION_INT, ATTITUDE and VFR_HUD packet and send them
                        m = state.control_link_out.vfr_hud_encode(state_entry.data['airspeed'],state_entry.data['groundspeed'],state_entry.data['heading'],state_entry.data['throttle'],
                                                                  state_entry.data['alt'],state_entry.data['climb'])
                        state.control_link_out.send(m)
                        
                        m = state.control_link_out.attitude_encode(state_entry.data['time_boot_ms'],state_entry.data['roll'],state_entry.data['pitch'],state_entry.data['yaw'],
                                                                  state_entry.data['rollspeed'],state_entry.data['pitchspeed'],state_entry.data['yawspeed'])
                        state.control_link_out.send(m)
                        
                        m = state.control_link_out.global_position_int_encode(state_entry.data['time_boot_ms'],state_entry.data['lat'],state_entry.data['lon'],state_entry.data['alt'],
                                                                  state_entry.data['relative_alt'],state_entry.data['vx'],state_entry.data['vy'],state_entry.data['vz'], state_entry.data['hdg'])
                        state.control_link_out.send(m)
    
        
    def update_current_state(self, msg_dict):
        state = self.state
        #update the current state timestamp
        state.current_state.time_stamp = int((time.time()%1000)*100)
        
        for key in msg_dict.keys():
            #update key value pairs
            state.current_state.data[key] = msg_dict[key]
        #print state.current_state.time_stamp, state.current_state.data
        
    def log_current_state(self):
        state = self.state
        #write the state to file here...
        pass
        
    def update_state_history(self):
        state = self.state
        while len(state.state_history) >= state.state_history_max_length:
            state.state_history.pop(0) #remove the first entry
        
        new_state = State(time_stamp=state.current_state.time_stamp, data=state.current_state.data)
        state.state_history.append(new_state) #add the new entry
    
    def get_state_from_history(self, lookup_time_stamp):
        #lookup and return closest entry to lookup_time_stamp
        state = self.state
        if len(state.state_history)==0:
	    return False
        if (lookup_time_stamp >= state.state_history[0].time_stamp and lookup_time_stamp <= state.state_history[-1].time_stamp):
            #the lookup value IS somewhere in the state history
            #get the closest value...
            print len(state.state_history), state.state_history[0].time_stamp, " to ", state.state_history[-1].time_stamp
            (idx, state_entry) = min(enumerate(state.state_history), key=lambda x: abs(x[1].time_stamp - lookup_time_stamp))
            return state_entry
	else:
            #lookup value is NOT in the state history... too old?
            return False
        
        
    def binary_search(self, arr, x, low=0, high=None):   # can't use arr to specify default for high
        high = high if high is not None else len(arr) # high defaults to len(arr)   
        pos = bisect_left(arr,x,low,high)          # find insertion position
        return (pos if pos != high and arr[pos] == x else -1) # don't walk off the end


            
        
           
       
       
    def is_alive(self):
        return self.state.alive
    

def main_loop():
    '''main processing loop'''
    #make a camera object
    aps = AP_State()
    while aps.is_alive():
        aps.process_control_connection_in()
        
        #time.sleep(0.1)
    


if __name__ == '__main__':
    from optparse import OptionParser
    parser = OptionParser('ap_state.py [options]')
     
    #run main loop as a thread
  
    main = threading.Thread(target = main_loop)
    main.daemon = True
    main.start()
    main.join()
