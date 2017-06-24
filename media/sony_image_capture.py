import cv2
import io
import Image
import numpy as np
import subprocess
from media_object import Media
import pexif
import sc_SonyQX1 as sony

class Camera():
    def __init__(self):
        self.camera = sony.SmartCamera_SonyQX(0,'wlan0')
        pass
    
    def capture(self):
        if self.camera.take_picture():
            #if taking the pic worked....
            bytes = self.camera.boGetLatestImage()
            if bytes:
                #if we got .jpg image data
                stream = io.BytesIO(bytes)
                
                img = Image.open(stream) #open the stream with PIL
                imgcv = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR) #make a numpy array from the PIL image and then convert to openCV format with RBG to BGR colour conversion
                
                image_str=pexif.JpegFile.fromString(bytes)

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