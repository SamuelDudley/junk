import vici
import multiprocessing
import time
#note unless you are root you will need to do the following: sudo chmod 777 /var/run/charon.vici

class VState(object):
    """holds the VPN state"""
    def __init__(self):
        self.alive = True
        self.session = vici.Session()
        self.possible_connections = []
        self.target_connections = ['rw-2']
        self.active_connections = []
    
class StrongSwan(object):
    def __init__(self,  queue = None):
        self.state = VState()
        self.get_possible_connections()
    
    def process_control_connection_in(self):
        '''handle incoming mavlink packets'''
        pass
    
    def check_interfaces(self):
        state = self.state
        for vpn_conn in state.session.list_sas():
            for key in state.active_connections:
#                 print 'key', key
#                 print vpn_conn[key]
#                 print vpn_conn[key]['established']
#                 print vpn_conn[key]['reauth-time']
#                 print vpn_conn[key]['state']
#                 print vpn_conn[key]['local-host']
#                 print vpn_conn[key]['remote-host']
                
                try:
                    child = vpn_conn[key]['child-sas']
                    if child == {}:
                        child = None
                except:
                    print 'tunnel not connected at child level!'
                    child = None
                
                if child is not None:
                    for child_key in child:
                        
                        print 'time: ', time.time(), 'child key', child_key, child[child_key]['bytes-in'], child[child_key]['bytes-out']
                     
                        #print 'packets'
                        #print 'in: ', child[child_key]['packets-in']
                        #print 'out: ', child[child_key]['packets-out']
                         
                        #print 'bytes'
                        #print 'in: ', child[child_key]['bytes-in']
                        #print 'out: ', child[child_key]['bytes-out']
                     
#                         print child[child_key]['mode']
                        #print 'ip: ', child[child_key]['local-ts']
#                         print child[child_key]['remote-ts']
                       # print 'key: ', child[child_key]['rekey-time']
                       # print 'life: ', child[child_key]['life-time']
                    
                
                if key in state.target_connections and child is None:
                    self.connection_down(key)
                    self.connection_up(key)
        
        for key in state.target_connections:
            if key not in state.active_connections:
                #the connection is inactive
                self.connection_up(key)
                
        
    def connection_up(self, key):
        state = self.state
        print 'up: ', key
        rep =state.session.initiate({'child':key, 'timeout':5000}) #loglevel
        #TODO: handle errors, log?
        print time.time(), rep
        
    def connection_down(self, key):
        state = self.state
        print 'down: ', key
        rep = state.session.terminate({'ike':key, 'timeout':5000}) #5second timeout...
        #TODO: handle errors, log?
        print time.time(), rep
    
    def get_possible_connections(self):
        '''reset and repopulate possible connections based on /etc/ipsec.conf'''
        state = self.state
        state.possible_connections = []
        for conn in state.session.list_conns():
            for key in conn:
                state.possible_connections.append(key)
        
#         print 'p',state.possible_connections
                
    def get_active_connections(self):
        state = self.state
        state.active_connections = []
        
        for conn in state.session.list_sas():
            for key in conn:
                state.active_connections.append(key)
        
#         print 'a', state.active_connections
                
    def is_alive(self):
        return self.state.alive

def main_loop():
    '''main processing loop'''
    #make a camera object
    VPN = StrongSwan()
    while VPN.is_alive():
        VPN.process_control_connection_in()
        VPN.get_possible_connections()
        VPN.get_active_connections()
        VPN.check_interfaces()
        time.sleep(1.0)
    


if __name__ == '__main__':
    from optparse import OptionParser
    parser = OptionParser('vpn_control.py [options]')
     
    #run main loop as a thread
    main = multiprocessing.Process(target=main_loop)
    main.start()
    main.join() 

"""
 #default socket is handled by the null init of Session class
print v.version()

print v.stats()

print v.list_conns()

possible_connections = []

for conn in v.list_conns():
    for key in conn:
        possible_connections.append(key)

print 'possible connections based on ipsec.conf: ',  possible_connections      



for key in possible_connections:
    print 'up ', key
    rep =v.initiate({'child':key, 'timeout':0}) #loglevel
    print rep
     
    print 'down ', key
    rep = v.terminate({'ike':key, 'timeout':0})
    print rep

print v.list_sas()

active_connections = []

for conn in v.list_sas():
    for key in conn:
        active_connections.append(key)

print 'active connections: ',  active_connections      

for vpn_conn in v.list_sas(): #active connections
    for key in active_connections:
        print 'key', key
        print vpn_conn[key]
        print vpn_conn[key]['established']
        print vpn_conn[key]['reauth-time']
        print vpn_conn[key]['state']
        print vpn_conn[key]['local-host']
        print vpn_conn[key]['remote-host']
        
        try:
            child = vpn_conn[key]['child-sas']
        except:
            print 'tunnel not connected at child level!'
            child = None
        
        if child is not None:
            for child_key in child:
                print 'child key', child_key
            
                print 'packets'
                print child[child_key]['packets-in']
                print child[child_key]['packets-out']
                
                print 'bytes'
                print child[child_key]['bytes-in']
                print child[child_key]['bytes-out']
            
                print 'tunnel'
                print child[child_key]['mode']
                print child[child_key]['local-ts']
                print child[child_key]['remote-ts']
                print child[child_key]['rekey-time']
                print child[child_key]['life-time']
"""
    
