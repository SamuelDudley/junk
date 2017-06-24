import cv2
import pexif
from media_object import Media
class Camera():
    def __init__(self):
        pass
    
    def capture(self):
        try:
            imgPath = 'fake/fake.jpg'
            imgcv = cv2.imread(imgPath) #open image from file
         
            image_str=pexif.JpegFile.fromFile(imgPath)
            
            return Media(data=imgcv, exif = image_str.exif)
        except:
            print 'capture error'
            return False

if __name__ == '__main__':
    cam = Camera()
    img = cam.capture()
    
    half_size = cv2.resize(img.data, (0,0), fx=0.5, fy=0.5)
    quater_size = cv2.resize(img.data, (0,0), fx=0.25, fy=0.25)
    #defined_size = cv2.resize(img.data, (resized_dim1, resized_dim2))
    
    cv2.imshow('image',quater_size)
    cv2.waitKey(0)