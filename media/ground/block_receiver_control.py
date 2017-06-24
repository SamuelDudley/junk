"""the media control block takes a connection from the camera(s)"""
import time
import multiprocessing
import block_sender
from media_object import Media
import math
import cv2
import numpy as np
import pickle
import pexif



class BState(object):
    """holds the blocker state"""
    def __init__(self, queue):
        self.alive = True
        
        self.media_queue = queue
        debug = True
        bandwidth = 320000
        ordered = False
        packet_loss = False
        backlog=100
        chunk_size=1000 #max = 65535
        dest_ip = '10.7.7.2'
        listen_ip = '10.7.7.1'
        # setup a send/recv pair
        self.block_connetion = block_sender.BlockSender(dest_ip = dest_ip,
                                                        listen_ip= listen_ip,
                                                        dest_port =7000,
                                                        port =6000,
                                                        debug=debug, bandwidth=bandwidth,
                                                        ordered=ordered, chunk_size=chunk_size,
                                                        backlog=backlog)

        if packet_loss:
            self.block_connetion.set_packet_loss(packet_loss)
            
        self.target_block_numbers = (3,3,1)
        self.raw_block_list  = []
        self.processed_block_list = []
        self.status_history = []
        self.completed_history = []
        self.thread_list = []
       
        
class Blocker(object):
    def __init__(self, queue = None):
        self.state = BState(queue)
        
    def configure_block_connetion(self):
        pass

        

    def process_media_queue(self):
        state = self.state
        while state.media_queue.qsize():
            #there is something still in the media queue
            obj = state.media_queue.get()
            if isinstance(obj, Media):
                #the object is a media object with .data and .meta
                #print obj.data
                #print obj.meta
                
                #block the object
                self.block_media(obj)
                self.process_blocks()
                #send the data
                self.send_blocks()
                self.notify_send_complete()
                
                
    def process_block_connetion(self):
        state = self.state
        
        
        
        

        blk = state.block_connetion.recv(0.01)
#         if blk is not None:
#             received1.append(blk)

        state.block_connetion.tick()
        
        for ID, DATA in state.block_connetion.completed2:
            if ID not in state.completed_history:
 
                #add id to history
                state.completed_history.append(ID)
                print "comp:",  [(ID >> i & 0xff) for i in (16,8,0)]
                 
                state.thread_list.append(threading.Thread(target=write_image, args=(DATA,ID)))
                state.thread_list[-1].setDaemon(True)
                state.thread_list[-1].start()
                
                

        for blk in state.block_connetion.incoming:
            percentage = (float(blk.data_length)/float(blk.size))*100
            id = blk.block_id           
            if (id, percentage) not in state.status_history:
                state.status_history.append((id, percentage))
                print id," : ", percentage,"%"
                
    
        
    def notify_send_complete(self):
        state = self.state

        state.control_link_out.digicam_control_send(100,101,1,0,0,1,1,self.command_id,0,0)
        self.command_id +=1
        
        if self.command_id > 255:
            self.command_id = 0
        
            
    def get_send_status(self):
        state = self.state
        state.block_connetion.report(detailed=True)
        
               
    def is_alive(self):
        return self.state.alive
    

def main_loop():
    '''main processing loop'''
    #make a blocker object
    blk = Blocker()
        

    while blk.is_alive():
        blk.process_block_connetion()
        #time.sleep(0.1)
        
def write_image(image_buffer,ID):
    image_str=pexif.JpegFile.fromString(image_buffer)
    pickled_meta = image_str.exif.primary.ExtendedEXIF.UserComment
    
#     with open('tmp/'+str(ID)+"f"+'.jpg', 'wb') as fid:
#         fid.write(li[0])
    block_dict = pickle.loads(''.join(pickled_meta))
    print block_dict
    image_index = block_dict['image_index']
    image_str.writeFile('tmp/'+str(image_index)+'.jpg')
    
    """
    if 'extended_meta' in block_dict.keys():
        #first image block...
        image_index = block_dict['image_index']
        width = block_dict['width']
        height = block_dict['height']
        block_dicts=block_dict['extended_meta']
        x = block_dict['x_pixel_index']
        y = block_dict['y_pixel_index']
        blank_image = np.zeros((height,width,3), np.uint8)
        s_img = cv2.imdecode(np.frombuffer(image_buffer, dtype='uint8'), cv2.CV_LOAD_IMAGE_COLOR)
        blank_image[x:x+s_img.shape[0], y:y+s_img.shape[1]] = s_img
        cv2.imwrite('tmp/'+str(image_index)+'.jpg', blank_image, [cv2.IMWRITE_JPEG_QUALITY, 100])
        
    else:
        image_index = block_dict['image_index']
        x = block_dict['x_pixel_index']
        y = block_dict['y_pixel_index']
        s_img = cv2.imdecode(np.frombuffer(image_buffer, dtype='uint8'), cv2.CV_LOAD_IMAGE_COLOR)
        imgcv = cv2.imread('tmp/'+str(image_index)+'.jpg')
        imgcv[x:x+s_img.shape[0], y:y+s_img.shape[1]] = s_img
        cv2.imwrite('tmp/'+str(image_index+x)+'.jpg', imgcv, [cv2.IMWRITE_JPEG_QUALITY, 100])
                
#         nparr = np.frombuffer(imgbuf, dtype='uint8')
#         img_np = cv2.imdecode(nparr, cv2.CV_LOAD_IMAGE_COLOR)
#         cv2.imwrite('tmp/'+str(ID)+'.jpg', img_np, [cv2.IMWRITE_JPEG_QUALITY, 100])
    """
    


if __name__ == '__main__':
    from optparse import OptionParser
    parser = OptionParser('block_sender_control.py [options]')
     
    #run main loop as a thread
    import threading
    main = threading.Thread(target = main_loop)
    main.daemon = True
    main.start()
    main.join()
    
    
    
    
    
    
    
    
        