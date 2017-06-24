from pymavlink import mavutil
import time
import threading
#import gphoto_image_capture
import fake_image_capture
#import sony_image_capture
import vfl_image_capture
import multiprocessing
from media_object import Media
import select
from numpy import mod
import numpy as np


class CState(object):
    """holds the camera state"""
    def __init__(self,  queue):
        self.capture_mode = 1 # 0 = wait for cmd and action, 1  = auto loop interval
        
        self.control_connection_in = mavutil.mavudp("127.0.0.1:14666")
        self.control_link_in = mavutil.mavlink.MAVLink(self.control_connection_in)
        self.control_connection_out = mavutil.mavudp("127.0.0.1:14676", input=False)
        self.control_link_out = mavutil.mavlink.MAVLink(self.control_connection_out)
        self.control_link_out.srcSystem = 122
        self.control_link_out.srcComponent = 100
        
        self.table_ports = [self.control_connection_in.port]
        
        self.capture_interval = 2 #seconds. used for auto capture
        self.alive = True
        self.current_meta_image_index = None
        self.target_system = 1
        self.target_component = 1
        self.camera_type = "vfl"
        self.media_queue = queue
        self.image_index = 0
        self.capture_time = time.time()
        self.media_buffer = []
        self.media_buffer_max_count = 5 #media objects
        self.media_buffer_max_age = 5 #seconds
        self.request_ap_meta  = True
        self.request_mount_meta = False #currently there is no mount...
        self.capture_retry_max = -1 #-1 = inf, 0 = no retry, 1, 2, 3, etc...
        self.capture_retry_count = 0
	self.prev_img = Media()
        
        if self.camera_type == 'canon':
            self.camera = gphoto_image_capture.Camera()
        if self.camera_type == 'fake':
            self.camera = fake_image_capture.Camera()
        if self.camera_type == 'sony':
            self.camera = sony_image_capture.Camera()
        if self.camera_type == 'vfl':
	    self.camera = vfl_image_capture.Camera()
        
        
class Camera(object):
    def __init__(self,  queue = None):
        self.state = CState(queue)

        
    
    def capture_image(self):
        state = self.state
        state.capture_time = float(time.time()) #TODO: this is not the true capture time...
        img = state.camera.capture()
	
	if isinstance(img, Media):
        #hack to stop dup. images
            if np.array_equal(img.data, state.prev_img.data):
	        return False
	    else:
	        state.prev_img = img
       
	if isinstance(img, Media):
            img.meta = {'image_index':state.image_index, 'capture_time':state.capture_time,
                                                                'width':img.data.shape[1],'height':img.data.shape[0],
                                                                'ap_meta_requested':False, 'ap_meta_complete':False,
                                                                'mount_meta_requested':False,'mount_meta_complete':False,
                                                                'time_out_time':time.time()+state.media_buffer_max_age}
            self.write_media_to_buffer(img)
             
                
            #TODO: fix this ^^^ to handle errors in the capture
            #and provide feedback via control link
            #make a media object with the data
            #and put it in the IPC queue
                
            state.image_index += 1
            state.capture_retry_count = 0
            return True
        
        else:
            return False
            
    
    def request_for_meta(self, meta):
        state = self.state
        
        
        print int((meta['capture_time']%1000)*100)
        m = state.control_link_out.command_long_encode(122, 3, 122, 0, int((meta['capture_time']%1000)*100), meta['image_index'], 0,0,0,0,0 )
        print "capture time", meta['capture_time']
        #this msg will need to send to the mount and ap
        
        state.control_link_out.send(m)
        

            
    def process_media_buffer(self):
        state = self.state
        for media in state.media_buffer:
            
            if (state.request_ap_meta == True):
                if media.meta['ap_meta_requested'] == False:
                    #meta has yet to be requested
                    self.request_for_meta(media.meta) #request meta
                    media.meta['ap_meta_requested'] = True
                    
                if media.meta['ap_meta_requested'] == True and media.meta['ap_meta_complete'] == False:
                    #check for time out
                    if time.time() > media.meta['time_out_time']:
                        media.meta['ap_meta_requested'] = 'time_out'
                        media.meta['ap_meta_complete'] = True
            else:
                media.meta['ap_meta_complete'] = True
        
        
        for media in state.media_buffer:
            if (state.request_mount_meta == True):
                if media.meta['mount_meta_requested'] == False:
                    #meta has yet to be requested
                    self.request_for_meta(media.meta) #request meta
                    media.meta['mount_meta_requested'] = True
                    
                if media.meta['mount_meta_requested'] == True and media.meta['mount_meta_complete'] == False:
                    #check for time out
                    if time.time() > (media.meta['capture_time']+state.media_buffer_max_age):
                        media.meta['mount_meta_requested'] = 'time_out'
                        media.meta['mount_meta_complete'] = True
            else:
                media.meta['mount_meta_complete'] = True
        
        
        for (idx, media) in enumerate(state.media_buffer):
            if (media.meta['ap_meta_complete'] == True and media.meta['mount_meta_complete'] == True):
                #we have all the meta / timeout has occured
                state.media_queue.put(state.media_buffer.pop(idx))
                return
        return
                    
    def do_capture(self):
	state = self.state
	while (not self.capture_image() and ((state.capture_retry_count < state.capture_retry_max) or (state.capture_retry_max < 0))):
	    #there was an error in the image capture
	    state.capture_retry_count += 1
	    #process... Retry?
    
    def process_control_connection_in(self):
        state = self.state
        #FIXME what is better here... using select or not... could put the receive part in a thread...
        #can also use select with the IPC queues...
        inputready,outputready,exceptready = select.select(state.table_ports,[],[],0) #timeout  = 0
        for s in inputready :
            if s == state.control_connection_in.port:
                 
                msg = state.control_connection_in.recv_msg()
        
                if msg != None:
                    msg_id = msg.get_msgId()
                    
                    msg_dict = msg.to_dict()
                    
                    msg_type = msg.get_type()
                    
                    
                    
                    print msg_type
                
                    
                    if msg_id == 155 and state.capture_mode == 0:
			self.do_capture()
                        
                            
               
                    #if we get the getta for this image from the AP state...
                    #then apply it
                    #the order from the AP state is COMMAND_LONG, VFR_HUD, ATTITUDE then GLOBAL_POSITION_INT
                    #we finalise the meta with GLOBAL_POSITION_INT because that is the minimum
                    #requirement of the geotag info
                    
                    if msg_type == 'COMMAND_LONG':
                        state.current_meta_image_index = msg_dict['param2']
                        self.apply_ap_meta({'ap_meta_time':msg_dict['param3']})
                        print msg_dict['param3'], msg_dict['param1']
                    
                    if msg_type == 'VFR_HUD':
                        self.apply_ap_meta(msg_dict)
                    
                    if msg_type == 'ATTITUDE':
                        self.apply_ap_meta(msg_dict)
                        
                    if msg_type == 'GLOBAL_POSITION_INT':
                        self.apply_ap_meta(msg_dict)
                        self.finalise_ap_meta(msg_dict)

	if state.capture_mode == 1:
	    #we need to auto cap
	    if time.time() >= state.capture_time + state.capture_interval:
		self.do_capture()
            
    def write_media_to_buffer(self, media):
        state = self.state
        if len(state.media_buffer)<state.media_buffer_max_count:
            state.media_buffer.append(media)
        else:
            state.media_buffer.pop(0) #get rid of the oldest media
            state.media_buffer.append(media)
        
    
    def apply_mount_meta(self, msg_dict):
        state = self.state
        for media in state.media_buffer:
            #if media.meta['image_index'] == msg_dict['image_index']:
            if media.meta['image_index'] == state.current_meta_image_index:
                #we have a match, now apply the meta...
                media.meta = dict(media.meta, **msg_dict)
                return True
        return False
    
    def finalise_mount_meta(self, msg_dict):
        state = self.state
        for media in state.media_buffer:
            #if media.meta['image_index'] == msg_dict['image_index']:
            if media.meta['image_index'] == state.current_meta_image_index:
                media.meta['mount_meta_complete'] = True
                return True
        return False
        
    def apply_ap_meta(self, msg_dict):
        state = self.state
        for media in state.media_buffer:
            #if media.meta['image_index'] == msg_dict['image_index']:
            if media.meta['image_index'] == state.current_meta_image_index:
                #we have a match, now apply the meta...
                media.meta = dict(media.meta, **msg_dict)
                return True
        return False
            
    def finalise_ap_meta(self, msg_dict):
        state = self.state
        for media in state.media_buffer:
            #if media.meta['image_index'] == msg_dict['image_index']:
            if media.meta['image_index'] == state.current_meta_image_index:
                media.meta['ap_meta_complete'] = True
                return True  
        return False
    
    def is_alive(self):
        return self.state.alive
    

def main_loop():
    '''main processing loop'''
    #make a camera object
    cam = Camera()
    while cam.is_alive():
        cam.process_control_connection_in()
        cam.process_media_buffer()
        print time.time()
        time.sleep(0.1)
    


if __name__ == '__main__':
    from optparse import OptionParser
    parser = OptionParser('camera_control.py [options]')
     
    #run main loop as a thread
    main = multiprocessing.Process(target=main_loop)
    main.start()
    main.join() 
    
    
#     main = threading.Thread(target = main_loop)
#     main.daemon = True
#     main.start()
#     main.join()
