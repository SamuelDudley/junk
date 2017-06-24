import cv2
import io
import Image
import numpy as np
import subprocess
from media_object import Media
import pexif


def capture():
    bashCommand = "gphoto2 --capture-image-and-download --force-overwrite --stdout"
    child = subprocess.Popen(bashCommand.split(), shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = child.communicate()
    #we only want the .jpeg binary buffer 
    stream = io.BytesIO(stdout[0]) #make an IO stream for the binary data
    img = Image.open(stream) #open the stream with PIL
    imgcv = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR) #make a numpy array from the PIL image and then convert to openCV format with RBG to BGR colour conversion
    image_str=pexif.JpegFile.fromString(stdout[0])

    return Media(data=imgcv, exif = image_str.exif)

if __name__ == '__main__':
    cam = Camera()
    img = cam.capture()
    
    half_size = cv2.resize(img.data, (0,0), fx=0.5, fy=0.5)
    quater_size = cv2.resize(img.data, (0,0), fx=0.25, fy=0.25)
    #defined_size = cv2.resize(img.data, (resized_dim1, resized_dim2))
    
    cv2.imshow('image',quater_size)
    cv2.waitKey(0)