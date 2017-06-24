import numpy as np
import cv2
from media_object import Media
import threading
import pexif
import time

class Camera():
    def __init__(self):
        self.camera = cv2.VideoCapture(0)
        self.camera.set(3,1920)
	self.camera.set(4,1080)
	time.sleep(2)
	self.imgPath = 'fake/fake.jpg'
	self.frame = None
	self.ret = False
        main = threading.Thread(target = self.capture_loop)
        main.daemon = True
        main.start()
        
    
    def capture_loop(self):
        # Capture frame-by-frame
        while True:
           self.ret, self.frame = self.camera.read()
           time.sleep(0.01)
 
    def capture(self):
        print self.ret
        if self.ret: 
           image_str=pexif.JpegFile.fromFile(self.imgPath) #use fake exif data

           # Our operations on the frame come here
           imgcv = cv2.cvtColor(self.frame,cv2.COLOR_BGR2BGRA)
	   return Media(data=imgcv, exif = image_str.exif)
        else:
	   return False

if __name__ == '__main__':
    cam = Camera()
    img = cam.capture()
    
    half_size = cv2.resize(img.data, (0,0), fx=0.5, fy=0.5)
    quater_size = cv2.resize(img.data, (0,0), fx=0.25, fy=0.25)
    #defined_size = cv2.resize(img.data, (resized_dim1, resized_dim2))
     
    cv2.imshow('image',quater_size)
    cv2.waitKey(0)
