import cv2
import io
import Image
import numpy as np
import subprocess
class Camera():
    def __init__(self):
        pass
    
    def capture(self):
        bashCommand = "gphoto2 --capture-image-and-download --force-overwrite --stdout"
        child = subprocess.Popen(bashCommand.split(), shell=False, stdout=subprocess.PIPE)
        bytes = child.communicate()[0] #we only want the .jpeg binary buffer
        stream = io.BytesIO(bytes) #make an IO stream for the binary data
        img = Image.open(stream) #open the stream with PIL
        #img = Image.frombuffer('I', (5184,3456), output, "raw", 'I', 0, 1)
        imgcv = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR) #make a numpy array from the PIL image and then convert to openCV format with RBG to BGR colour conversion
        image_str=pexif.JpegFile.fromString(bytes)

        return Media(data=imgcv, exif = image_str.exif)

if __name__ == '__main__':
    cam = Camera()
    img = cam.capture()
    
    half_size = cv2.resize(img, (0,0), fx=0.5, fy=0.5)
    quater_size = cv2.resize(img, (0,0), fx=0.25, fy=0.25)
    #defined_size = cv2.resize(img, (resized_dim1, resized_dim2))
    
    cv2.imshow('image',quater_size)
    cv2.waitKey(0)