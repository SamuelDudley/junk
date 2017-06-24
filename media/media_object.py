class Media(object):
    def __init__(self, data = None, meta = {}, exif = None):
        self.data = data
        self.meta = meta
        self.exif = exif
        
    def set_data(self, data):
        self.data = data
        
        
    def get_data(self):
        return self.data
    
    def set_meta(self, meta):
        self.meta = meta
        
        
    def get_meta(self):
        return self.meta
    
    def set_exif(self, exif):
        self.exif = exif
        
        
    def get_exif(self):
        return self.exif