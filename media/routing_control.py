"""sit and wait for mavlink msg then action it"""

from pymavlink import mavutil
import time
import threading
import numpy as np
import select




class RState(object):
    """holds the router state"""
    def __init__(self):
        self.connections = []
        self.alive = True
        #the routing table is as follows:
        #system_id, component_id, connection_instance
        self.routing_table = np.array([["system_id", "component_id", "connection_instance"]])
        self.debug = True
        self.ap_system_id = 1
        self.ap_component_id = 1
        self.ap_state_system_id = 122
        self.ap_state_component_id = 3
        self.camera_system_id = 122
        self.camera_component_id = 100
        
class Connection(object):
    def __init__(self, connection, link, system_id, component_id, input = True, output = False, external = False, internal = True):
        self.connection = connection
        self.link = link
        self.system_id = system_id
        self.component_id = component_id
        self.msg = None
        self.external = external
        self.internal = internal
        self.input = input
        self.output = output
        
        
    def is_external(self):
        return self.external
    
    def is_internal(self):
        return self.internal
     
    def receive_callback(self, msg):
        '''this is run when a new msg is received'''
        state = self.state
        pass

        
class Router(object):
    def __init__(self):
        self.state = RState()        
        self.create_connection()
    
        
    
    def create_connection(self):
        state = self.state
        
        ## camera
        connection = mavutil.mavudp("127.0.0.1:14676", input= True)
        link = mavutil.mavlink.MAVLink(connection)
        new_connection = Connection(connection, link, system_id = 122, component_id = 101, input=True)
        self.add_connection_to_table(new_connection)
        
        connection = mavutil.mavudp("127.0.0.1:14666", input= False)
        link = mavutil.mavlink.MAVLink(connection)
        new_connection = Connection(connection, link, system_id = 122, component_id = 100, output=True)
        self.add_connection_to_table(new_connection)
        
        ## media manager
        connection = mavutil.mavudp("127.0.0.1:14677", input= True)
        link = mavutil.mavlink.MAVLink(connection)
        new_connection = Connection(connection, link, system_id = 122, component_id = 201, input=True)
        self.add_connection_to_table(new_connection)
        
        connection = mavutil.mavudp("127.0.0.1:14667", input= False)
        link = mavutil.mavlink.MAVLink(connection)
        new_connection = Connection(connection, link, system_id = 122, component_id = 200, output=True)
        self.add_connection_to_table(new_connection)
        
        ## block sender
        connection = mavutil.mavudp("127.0.0.1:14678", input= True)
        link = mavutil.mavlink.MAVLink(connection)
        new_connection = Connection(connection, link, system_id = 122, component_id = 253, input=True)
        self.add_connection_to_table(new_connection)
        
        connection = mavutil.mavudp("127.0.0.1:14668", input= False)
        link = mavutil.mavlink.MAVLink(connection)
        new_connection = Connection(connection, link, system_id = 122, component_id = 254, output=True)
        self.add_connection_to_table(new_connection)
        
        ## mount (gimbal)
        
        
        ## ap bi-directional
        connection = mavutil.mavserial("/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_A4006JAo-if00-port0",baud=57600)
        link = mavutil.mavlink.MAVLink(connection)
        new_connection = Connection(connection, link, system_id = 122, component_id = 1, input=True, output=True)
        self.add_connection_to_table(new_connection)
        
        
        ## ap_state
        connection = mavutil.mavudp("127.0.0.1:14779", input= True)
        link = mavutil.mavlink.MAVLink(connection)
        new_connection = Connection(connection, link, system_id = 122, component_id = 2, input=True)
        self.add_connection_to_table(new_connection)
        
        connection = mavutil.mavudp("127.0.0.1:14769", input= False)
        link = mavutil.mavlink.MAVLink(connection)
        new_connection = Connection(connection, link, system_id = 122, component_id = 3, output=True)
        self.add_connection_to_table(new_connection)
        
        
        ## external interface (to redirector)
        
    def add_connection_to_table(self, connection):
        
        state = self.state
        table_entry = np.array([[connection.system_id,
                                connection.component_id,
                                connection]])
        
        
        state.routing_table  = np.append(state.routing_table, table_entry, axis=0)
        
        if state.debug:
            print state.routing_table
                
    def process_connections(self):
        state = self.state
        table_connections = state.routing_table[1:,2] #all of the third col
        table_ports = [connection.connection.port for connection in table_connections]
        inputready,outputready,exceptready = select.select(table_ports,[],[])
        for s in inputready:
            for connection in table_connections:
                if (s == connection.connection.port and connection.input == True):
            
                #if connection.input:
                    
                    #if the connection can / should read input
                    msg = connection.connection.recv_msg()
                        
                    if msg != None:
                        msg_type = msg.get_type()
                        msg_id = msg.get_msgId()
                        msg_dict = msg.to_dict()
                        msg_source_system  = msg.get_srcSystem()
                        msg_source_component = msg.get_srcComponent()
                        
                        if state.debug:
                            print msg_type
                        
                        if ('target_system' and 'target_component') in msg_dict.keys():
                            msg_target_system = msg_dict['target_system']
                            msg_target_component = msg_dict['target_component']
                        else:
                            msg_target_system = False
                            msg_target_component = False
                            
                        if state.debug:
                            print msg_source_system, msg_source_component, msg_type, msg_target_system, msg_target_component
                        
                        
                        
                        if (msg_source_system == state.ap_system_id and msg_source_component == state.ap_component_id):
                            #if the msg is from the AP...
                            #set the target destination (sys, comp) state module in this case...
                            forward_connection = self.get_connection_from_ids(state.ap_state_system_id, state.ap_state_component_id)
#                             if state.debug:
#                             print 'sending on msg from ap...'
                            forward_connection.link.srcSystem = msg_source_system
                            forward_connection.link.srcComponent = msg_source_component 
    
                            forward_connection.link.send(msg)
                            
                        elif (msg_source_system == state.ap_state_system_id and msg_source_component == state.ap_state_component_id):
                            #if the msg is from the AP state module... in reply to a request from the camera module
                            #set the target destination (sys, comp) camera module in this case...
                            forward_connection = self.get_connection_from_ids(state.camera_system_id, state.camera_component_id)
                            if state.debug:
                                print 'sending on msg from ap state...'
                            forward_connection.link.srcSystem = msg_source_system
                            forward_connection.link.srcComponent = msg_source_component 
    
                            forward_connection.link.send(msg)
                        
                        
                            
    
                        elif (msg_target_system and msg_target_component):
                            print ""
                            print ""
                            print msg_target_system, msg_target_component
                            #check the routing table for the system and component ID
                            forward_connection = self.get_connection_from_ids(msg_target_system, msg_target_component)
                            if forward_connection:
                                #there was an id match
                                if forward_connection.output:
                                    #connection accepts incoming data
                                    if state.debug:
                                        print 'sending on msg...'
                                    forward_connection.link.srcSystem = msg_source_system
                                    forward_connection.link.srcComponent = msg_source_component 
    
                                    forward_connection.link.send(msg)
                        else:
                            pass
                            #throw the msg away...
                                
    def get_connection_from_ids(self, system_id, component_id):
        state = self.state
        #for entry in routing table
        #look for a match to the pair
        #at this stage we are just sending the info to the first connection with the right id's
        #TODO: impliment a better / more complex routing rule set
        
        ################### routing table ##################
        #"system_id", "component_id", "connection_instance"#
        # system_id,   component_id,   connection_instance #
        # system_id,   component_id,   connection_instance #
        # ...                                              #
        # system_id,   component_id,   connection_instance #
        ####################################################
        
        table_system_ids = state.routing_table[1:,0] #all of the first col
        table_component_ids = state.routing_table[1:,1] #all of the second col
        table_connections = state.routing_table[1:,2] #all of the third col
        for (table_system_id, table_component_id, table_connection) in zip(table_system_ids, table_component_ids, table_connections):
            if (table_system_id == system_id and table_component_id == component_id):
                
#                 if state.debug:
#                     print "found matching connection for msg..."
#                     print table_connection.input,table_connection.output
                    
                return table_connection
        #if we got here there was no id match
        return False
       
    def is_alive(self):
        return self.state.alive
    

def main_loop():
    '''main processing loop'''
    #make a router object
    rout = Router()
    while rout.is_alive():
        rout.process_connections()
        #time.sleep(0.1) #dont need this if select is used...
    


if __name__ == '__main__':
    from optparse import OptionParser
    parser = OptionParser('routing_control.py [options]')
     
    #run main loop as a thread
    main = threading.Thread(target = main_loop)
    main.daemon = True
    main.start()
    main.join()
