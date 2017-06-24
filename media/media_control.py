"""the media control block takes a connection from the camera(s)"""
from pymavlink import mavutil
import time
import multiprocessing
from media_object import Media
import json
import cv2
import pickle
import pexif

class MMState(object):
    """holds the media state"""
    def __init__(self, queue_in, queue_out):
        self.storage = 1# 1 = keep, 0 = don't keep
        self.alive = True
        self.control_connection_in = mavutil.mavudp("127.0.0.1:14667")
        self.control_link_in = mavutil.mavlink.MAVLink(self.control_connection_in)
        self.control_connection_out = mavutil.mavudp("127.0.0.1:14677", input=False)
        self.control_link_out = mavutil.mavlink.MAVLink(self.control_connection_out)
        self.control_link_out.srcSystem = 122
        self.control_link_out.srcComponent = 200

        self.new_media = False
        self.media_queue_in = queue_in
        self.media_queue_out = queue_out
        self.media_buffer = []
        self.media_buffer_max = 5
        self.send_media = True #if true we will try to send media
        #to the block sender
        
class Media_Manager(object):
    def __init__(self, queue_in = None, queue_out = None):
        self.state = MMState(queue_in, queue_out)
        self.command_id = 0
    
    def process_media_queues(self):
        self.process_media_queue_in()
        self.process_media_queue_out()
        
    def process_media_queue_in(self):
        state = self.state
        while state.media_queue_in.qsize():
            #there is something still in the media queue
            obj = state.media_queue_in.get()
            if isinstance(obj, Media):
                print "got media"
                if state.storage:
                    self.write_media_to_data_base(obj)
                self.write_media_to_buffer(obj)
        

    def write_media_to_data_base(self, media):
        #convert the meta to pickle binary
        meta_binary = str.encode(pickle.dumps(media.meta))
        #convert image to binary
        (flag, media_buffer) = cv2.imencode('.jpg', media.data, [cv2.IMWRITE_JPEG_QUALITY, 100])
        #write exif data back onto
        image_binary = media_buffer.tobytes()
        image_str=pexif.JpegFile.fromString(image_binary)
        image_str.import_exif(media.exif)
        image_str.exif.primary.ExtendedEXIF.UserComment = meta_binary
            
        with open("db/"+str(media.meta['image_index'])+".jpeg",'wb') as fid:
            
            media_string = image_str.writeString()
            
            fid.write(media_string)

        
    def read_media_from_data_base(self, image_index):
        new_media = Media()
        image_str=pexif.JpegFile.fromFile("db/"+str(image_index)+".jpeg")
        meta = image_str.exif.primary.ExtendedEXIF.UserComment
        new_media.meta = pickle.loads(''.join(meta))
        new_media.data = cv2.imread("db/"+str(image_index)+".jpeg")
        new_media.exif = image_str.exif
        return new_media
    
    def write_media_to_buffer(self, media):
        state = self.state
        if len(state.media_buffer)<state.media_buffer_max:
            state.media_buffer.append(media)
        else:
            state.media_buffer.pop(0) #get rid of the oldest media
            state.media_buffer.append(media)
	
            
    def process_media_queue_out(self):
        state = self.state
        if state.send_media:
            try:
                media = state.media_buffer.pop()
                #TODO make it a priority basis depending on
                #media content
            except:
                media = None
            if media is not None:
                state.media_queue_out.put(media)
                state.send_media = False #hold off sending another
                #until we hear back from the block sender
        
    
    def process_control_connection_in(self):
        state = self.state

        msg = state.control_connection_in.recv_msg()
    
            
        if msg != None:
            msg_id = msg.get_msgId()
            
            msgDict = msg.to_dict()
            
            print msg_id
            print msgDict
            
            if msg_id == 155:
                state.control_link_out.digicam_control_send(122,100,1,0,0,1,1,self.command_id,0,0)
                self.command_id +=1
                
                if self.command_id > 255:
                    self.command_id = 0
                
                state.send_media = True
                
    
    def process_media(self):
        state = self.state
        if state.new_media:
            #there is new media      
            if state.storage == True: #make a copy of the media
                #do something with the media here
                pass
            if state.send == True:
                #send the new media to the datalink
                pass

       
    def is_alive(self):
        return self.state.alive
    

def main_loop():
    '''main processing loop'''
    #make a media object
    med = Media()
        

    while med.is_alive():
        med.process_control_connection()
        med.process_media()
        time.sleep(0.1)
    


if __name__ == '__main__':
    from optparse import OptionParser
    parser = OptionParser('media_control.py [options]')
     
    #run main loop as a thread
    main = threading.Thread(target = main_loop)
    main.daemon = True
    main.start()
    main.join()
    
    
    
    
    
    
    
    
        
