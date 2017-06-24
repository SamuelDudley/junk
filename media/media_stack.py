'''
this stack runs a number of processes...
camera
    interchangeable front end
media manager
    image DB
media sender
    blocker

to limit socket transfers of large media files
the components have been intergrated allowing for
interprocess communication via qeues
'''


import multiprocessing
import camera_control
import media_control
import block_sender_control
import ap_state
import time

def ap_state_main_loop():
    '''main processing loop'''
    #make a camera object
    aps = ap_state.AP_State()
    while aps.is_alive():
        aps.process_control_connection_in()


def camera_main_loop():
    '''main processing loop'''
    #make a camera object
    cam = camera_control.Camera(queue = media_queue_upper)
    while cam.is_alive():
        cam.process_control_connection_in()
        cam.process_media_buffer()
        time.sleep(0.1)
        
def media_main_loop():
    '''main processing loop'''
    #make a blocker object
    med = media_control.Media_Manager(queue_in = media_queue_upper,
                                      queue_out = media_queue_lower)
    while med.is_alive():
        med.process_control_connection_in()
        med.process_media_queues()
        time.sleep(0.1)
        
def blocker_main_loop():
    '''main processing loop'''
    #make a blocker object
    blk = block_sender_control.Blocker(queue = media_queue_lower)
    while blk.is_alive():
        blk.process_control_connection_in()
        blk.process_media_queue()
        time.sleep(0.01)



if __name__ == '__main__':
    from optparse import OptionParser
    parser = OptionParser('camera_control.py [options]')
    media_queue_upper = multiprocessing.Queue()
    media_queue_lower = multiprocessing.Queue()
    #run main loop as a thread
    ap_state_main = multiprocessing.Process(target=ap_state_main_loop)
    ap_state_main.daemon = True
    camera_main = multiprocessing.Process(target=camera_main_loop)
    camera_main.daemon = True
    media_main = multiprocessing.Process(target=media_main_loop)
    media_main.daemon = True
    blocker_main = multiprocessing.Process(target=blocker_main_loop)
    blocker_main.daemon = True    

    ap_state_main.start()
    time.sleep(1)
    
    camera_main.start()
    media_main.start()
    blocker_main.start()
    
    ap_state_main.join()
    camera_main.join() 
    media_main.join()
    blocker_main.join()
    
