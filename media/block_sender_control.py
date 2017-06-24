"""the media control block takes a connection from the camera(s)"""
from pymavlink import mavutil
import time
import multiprocessing
import block_sender
from media_object import Media
import math
import cv2
import numpy as np
import json
import struct
import base64
import pexif
import pickle




class BState(object):
    """holds the blocker state"""
    def __init__(self, queue):
        self.alive = True
        self.control_connection_in = mavutil.mavudp("127.0.0.1:14668")
        self.control_link_in = mavutil.mavlink.MAVLink(self.control_connection_in)
        self.control_connection_out = mavutil.mavudp("127.0.0.1:14678", input=False)
        self.control_link_out = mavutil.mavlink.MAVLink(self.control_connection_out)
        self.control_link_out.srcSystem = 122
        self.control_link_out.srcComponent = 254
	
	self.block_timeout = 10. #seconds (-1 = inf)
	self.idle_timeout = 2.
        self.block_time = time.time()
	self.recv_count = 0
	self.send_count = 0
	self.send_timer = time.time()
	self.recv_timer = time.time()
	self.notify_flag =False
	self.idle=False

        self.media_queue = queue
        debug = True
        bandwidth = 320000
        ordered = False
        packet_loss = False
        backlog=100
        chunk_size=1000 #max = 65535
        dest_ip = '10.7.7.1'
        listen_ip = '10.7.7.2'
        # setup a send/recv pair
        self.block_connetion = block_sender.BlockSender(dest_ip = dest_ip,
                                                        listen_ip= listen_ip,
                                                        dest_port = 6000,
                                                        port =7000,
                                                        debug=debug, bandwidth=bandwidth,
                                                        ordered=ordered, chunk_size=chunk_size,
                                                        backlog=backlog)

        if packet_loss:
            self.block_connetion.set_packet_loss(packet_loss)
            
        self.target_block_numbers = (1,1, 1)
        self.raw_block_list  = []
        self.processed_block_list = []
        
        
        self.high_block_priority = 3
        self.first_block_priority = 2
        self.normal_block_priority = 1
        self.low_block_priority = 0
        
class Blocker(object):
    def __init__(self, queue = None):
        self.state = BState(queue)
        self.command_id = 0
        self.notify_send_complete()
        
    def configure_block_connetion(self):
        pass

        

    def process_media_queue(self):
        state = self.state
        while state.media_queue.qsize():
            #there is something still in the media queue
            obj = state.media_queue.get()
            if isinstance(obj, Media):
                #the object is a media object with .data and .meta
                
                #block the object
                self.block_media(obj)
                self.process_blocks()
                #send the data
                self.send_blocks()
		state.notify_flag = True
	        
	if state.notify_flag == False and state.idle:
	    state.notify_flag = True
	
	if state.notify_flag:
	    self.notify_send_complete()
	    state.idle = False
	    state.notify_flag = False

	self.check_idle()

    def check_idle(self):
	state = self.state
	if state.block_connetion.recv_count != state.recv_count:
	    state.recv_count = state.block_connetion.recv_count
	    state.recv_timer = time.time()

	if state.block_connetion.send_count != state.send_count:
	    state.send_count = state.block_connetion.send_count
	    state.send_timer = time.time()

	current_time = time.time()

	if ((current_time - state.recv_timer > state.idle_timeout) or (current_time - state.recv_timer > state.idle_timeout)):
	    state.idle = True
	    state.send_timer = time.time()
            state.recv_timer = time.time()
	else:
	    state.idle = False
	
	            
                
    def process_blocks(self):
        state = self.state
        while len(state.raw_block_list)>0:
            raw_block = state.raw_block_list.pop(0)
            print raw_block.meta
            
            media_data = raw_block.data
            #print media_data
            image_index = raw_block.meta['image_index']
            x_pixel_index = raw_block.meta['x_pixel_index']
            y_pixel_index = raw_block.meta['y_pixel_index']
            x_loc_index = raw_block.meta['x_loc_index']
            y_loc_index = raw_block.meta['y_loc_index']
            (flag, img_buffer) = cv2.imencode('.jpg', media_data, [cv2.IMWRITE_JPEG_QUALITY, 95])
            #block_name = (image_index << 16) + (x_pixel_index << 8) + y_pixel_index
            #block_name = (image_index << 16) + (x_loc_index << 8) + y_loc_index
            block_name = (image_index << 8) + y_loc_index
            image_binary = img_buffer.tobytes()#np.getbuffer(img_buffer)[:]
            #print image_binary
            meta_binary = self.dict_to_binary(raw_block.meta)
            image_str=pexif.JpegFile.fromString(image_binary)
            if raw_block.exif is not None:
                image_str.import_exif(raw_block.exif)
                image_str.exif.primary.ExtendedEXIF.UserComment = meta_binary
            
#             print image_binary
#             print meta_binary
            #combined = image_binary+'META'+meta_binary
            
            combined = image_str.writeString()
            state.processed_block_list.append(Media(data = combined, meta = dict(raw_block.meta, **{'block_name':block_name})))
            
        
    def dict_to_binary(self, the_dict):
        pickle_string = pickle.dumps(the_dict)
        return str.encode(pickle_string)
          
    def send_blocks(self):
        state = self.state
	state.block_time = time.time()
	state.recv_count = 0
	state.send_count = 0
    
        while len(state.processed_block_list) > 0:
            processed_block = state.processed_block_list.pop(0)
            state.block_connetion.send(processed_block.data, 
                                       block_id = processed_block.meta['block_name'],
                                       priority = processed_block.meta['priority']
                                       ) #send the blocks to the other device
            
        while state.block_connetion.sendq_size() > 0:
            state.block_connetion.tick()
	    #print state.block_connetion.recv_count, state.block_connetion.send_count
	    if state.block_connetion.recv_count != state.recv_count:
	        state.recv_count = state.block_connetion.recv_count
		state.block_time = time.time()

	    if ((state.block_timeout!= -1) and (time.time()-state.block_time > state.block_timeout)):
		for idx, blk in enumerate(state.block_connetion.outgoing):
		    if blk.block_id == processed_block.meta['block_name']:
		        state.block_connetion.outgoing.pop(idx)
		print 'Block timeout...'
		print ''		
		return False
	    #we want to bail out of the block is taking too long...

    def notify_send_complete(self):
        state = self.state

        state.control_link_out.digicam_control_send(122,200,1,0,0,1,1,self.command_id,0,0)
        self.command_id +=1
        
        if self.command_id > 255:
            self.command_id = 0
        
            
    def get_send_status(self):
        state = self.state
        state.block_connetion.report(detailed=True)
        
    def process_control_connection_in(self):
        state = self.state

        msg = state.control_connection_in.recv_msg()
    
        if msg != None:
            msg_id = msg.get_msgId()
            
            msgDict = msg.to_dict()
            
            #print msg_id
            #print msgDict
 
    def block_media(self, media):
        state = self.state
        (num1, num2, flag) = state.target_block_numbers
        if flag == 0:
            #aim for block pixel count
            avg1 = math.ceil(len(media.data[:,0]) / num1)
            avg2 = math.ceil(len(media.data[0,:]) / num2)
        else:
            #aim for number of blocks
            avg1 = math.ceil(len(media.data[:,0]) / float(num1))
            avg2 = math.ceil(len(media.data[0,:]) / float(num2))
    
        last1 = 0.0
        dim1_index = 0
        dim2_index = 0
        master_block_meta_list = []
        while last1 < len(media.data[:,0]):
    
            last2 = 0.0
            while last2 < len(media.data[0,:]):
                if (dim1_index == 0 and dim2_index ==0):
                    #first block in image
                    priority = state.first_block_priority
                    
                    block_meta = {'image_index':media.meta['image_index'],'priority':priority, 'x_pixel_index':int(last2),'x_loc_index':int(dim1_index),'y_pixel_index':int(last1),'y_loc_index':int(dim2_index)}
                    first_block = Media(data = media.data[int(last1):int(last1 + avg1), int(last2):int(last2 + avg2)],
                                                  meta = dict(media.meta, **block_meta),
                                                  exif = media.exif)
                                                  
                else:
                    
                    priority = state.normal_block_priority
                    
                    block_meta = {'image_index':media.meta['image_index'], 'priority':priority, 'x_pixel_index':int(last1),'x_loc_index':int(dim1_index),'y_pixel_index':int(last2),'y_loc_index':int(dim2_index)}
                    state.raw_block_list.append(Media(data = media.data[int(last1):int(last1 + avg1), int(last2):int(last2 + avg2)],
                                                      meta = block_meta,
                                                      exif = media.exif))
                    master_block_meta_list.append(block_meta)
                    
                last2 += avg2
                dim2_index +=1
            last1 += avg1
            dim1_index +=1
            
            
            
        extended_meta = {'extended_meta':master_block_meta_list}
        first_block.meta = dict(first_block.meta, **extended_meta)            
        state.raw_block_list.append(first_block)
        
    
       
    def is_alive(self):
        return self.state.alive
    

def main_loop():
    '''main processing loop'''
    #make a blocker object
    blk = Blocker()
        

    while blk.is_alive():
        blk.process_control_connection_in()
        time.sleep(0.1)
    


if __name__ == '__main__':
    from optparse import OptionParser
    parser = OptionParser('block_sender_control.py [options]')
     
    #run main loop as a thread
    import threading
    main = threading.Thread(target = main_loop)
    main.daemon = True
    main.start()
    main.join()
    
    
    
    
    
    
    
    
        
