"""
https://github.com/JohnDMcMaster/uvscada/tree/master/scopetek
https://github.com/walac/pyusb/blob/master/docs/tutorial.rst



"""
import sys
import threading
import time
import Queue
import usb.core
import numpy as np


permission_error_msg = """Permission denied to access camera.

To fix this on Linux:
1. Edit /etc/udev/rules.d/50-scopetek.rules, add the following (you may need to choose a different group):
    SUBSYSTEMS=="usb", ATTRS{idVendor}=="0547", GROUP="plugdev", MODE="0666"
2. Restart udev:
    sudo udevadm control --reload
3. Unplug/replug the device and try again.
"""

class Scopetek:
    """Driver for scopetek / amscope / anchor microscope cameras. 
    
    Tested on:
        0547:c004  5MP-B CMOS Camera
    """
    def __init__(self):
        dev = usb.core.find(idVendor=0x547)
        if dev is None:
            print "No cameras found!"
            sys.exit(-1)

        cfg = dev[0]
        iface = cfg[(0,0)]
        ep = iface[0]

        try:
            cfg.set()
        except usb.core.USBError as err:
            if err.errno == 13:
                print permission_error_msg
                sys.exit(-1)
        
        self.dev = dev
        self.ep = ep
        self._last_frame = None
        self._last_frame_time = None
        self._fps = None
        self.white_balance = [1, 1, 1]

    def setup(self, resolution, exposure, fast, gain):
        # translate to packet arguments
        res = {
            (640,480): 0xc8,
            (1024,768): 0xc7,
            (1280,960): 0xc6,
            (2592,1944): 0xc0,
        }[resolution]
        if fast:
            exp = int(exposure * 23382)
            fst = 0xa1
        else:
            exp = int(exposure * 11694)
            fst = 0xa0
        gn = gain + 0x0f
        
        self._setup(res, exp, fst, gn)
        
        self.resolution = resolution
        self.fast = fast
        self.exposure = exposure
        self.gain = gain
        
    def _setup(self, res, exp, fst, gn):
        # basic control transfer sequence needed to configure and start the camera
        setup_ctrl = [
            (0x40, 180, res  , 0   , 10,  0           ),   # set resolution
            (0x40, 179, 0    , 0   , 10,  0           ),   # queue next frame?
            (0x40, 183, 0x19 , 0x6 , 0 ,  0           ),
            (0xc0, 182, 0    , 0x11, 10,  b'\x24\x03' ),
            (0x40, 181, fst  , 0   , 10,  0           ),   # set normal/fast frame speed mode
            (0x40, 183, 0x28 , 0x35, 10,  0           ),   
            (0x40, 183, 0x34 , 0x9 , 10,  0           ),
            (0x40, 181, 0xa0 , 0   , 10,  0           ),
            (0x40, 183, gn   , 0x35, 10,  0           ),   # set gain
            (0x40, 183, exp  , 0x9 , 10,  0           ),   # set exposure
        ]

        # send control transfer packets
        for ct in setup_ctrl:
            if ct[0] & 0x80 > 0:
                self.dev.ctrl_transfer(bmRequestType=ct[0], bRequest=ct[1], wValue=ct[2], wIndex=ct[3], data_or_wLength=ct[5])
            else:
                result = self.dev.ctrl_transfer(bmRequestType=ct[0], bRequest=ct[1], wValue=ct[2], wIndex=ct[3])

    def stop(self):
        self.dev.ctrl_transfer(bmRequestType=0x40, bRequest=187, wValue=0, wIndex=0)

    def read_frame(self):
        """Read one frame from the video stream.
        
        Colors are in bayer filter pattern:
            RGRGRG
            GBGBGB
            RGRGRG
            GBGBGB
        """
        # read one frame
        extra = 256 if self.resolution[0] == 2592 else 512
        data = self.ep.read(self.resolution[0] * self.resolution[1] + extra)

        # queue the next frame immediately
        self.dev.ctrl_transfer(bmRequestType=0x40, bRequest=179, wValue=0, wIndex=0)
        
        # make a Frame instance
        d1 = np.frombuffer(data, dtype='ubyte')
        d2 = d1[extra:].reshape(self.resolution[1], self.resolution[0])
        frame = Frame(d2, wb=self.white_balance)

        # measure FPS
        now = frame.time
        if self._last_frame_time is not None:
            self._fps = 1.0 / (now - self._last_frame_time)
        self._last_frame_time = now
        
        self._last_frame = frame
        return frame
        
    def auto_white_balance(self):
        if self._last_frame is None:
            self.read_frame()
        lf = self._last_frame.image()
        r, g, b = np.median(lf[...,0]), np.median(lf[...,1]), np.median(lf[...,2])
        mx = max([r, g, b])
        self.white_balance = [mx/r, mx/g, mx/b]


class StreamThread(threading.Thread):
    def __init__(self, cam):
        self.cam = cam
        self._stop = False
        self.stop_lock = threading.Lock()
        self.frames = Queue.Queue()
        threading.Thread.__init__(self)
        self.daemon = True
        self._last_frame_time = None

    def start(self):
        with self.stop_lock:
            self._stop = False
        threading.Thread.start(self)

    def run(self):
        while True:
            with self.stop_lock:
                if self._stop is True:
                    break
            frame = self.cam.read_frame()
            self.frames.put(frame)
    
    def stop(self):
        with self.stop_lock:
            self._stop = True

    def get_first(self):
        """Return the oldest frame in the queue, or None if the queue is empty.
        """
        try:
            return self.frames.get(block=False)
        except Queue.Empty:
            return None
        
    def get_all(self):
        """Remove all frames from the queue ant return them in a list.
        """
        frames = []
        while True:
            try:
                frames.append(self.frames.get(block=False))
            except Queue.Empty:
                break
        return frames


class Frame(object):
    def __init__(self, data, wb=None):
        self.time = time.time()
        self.data = data
        self.rgb = None
        if wb is None:
            self.white_balance = [1, 1, 1]
        else:
            self.white_balance = wb
        
    def image(self):
        if self.rgb is None:
            self.rgb = self.apply_wb(self.bayer_to_rgb(self.data))
        return self.rgb    
        
    def apply_wb(self, img):
        wb = img * np.array(self.white_balance).reshape(1, 1, 3)
        return wb

    @staticmethod
    def bayer_to_rgb(d2):
        # R G R G R G
        # g B g B g B
        # R G R G R G
        # g B g B g B
        # R G R G R G
        # g B g B g B
        d2 = d2.astype('uint16')
        
        r = d2[::2, ::2]
        g1 = d2[1::2, ::2]
        g2 = d2[::2, 1::2]
        b = d2[1::2, 1::2]
        
        d3 = np.zeros(d2.shape + (3,), dtype='ubyte')
        d3[::2, ::2, 0] = r
        d3[1:-1:2, ::2, 0] = (r[:-1, :] + r[1:, :]) // 2
        d3[::2, 1:-1:2, 0] = (r[:, :-1] + r[:, 1:]) // 2
        d3[1:-1:2, 1:-1:2, 0] = (r[:-1, :-1] + r[1:, :-1] + r[:-1, 1:] + r[1:, 1:]) // 4
        
        d3[1::2, ::2, 1] = g1
        d3[::2, 1::2, 1] = g2
        d3[1:-1:2, 1:-1:2, 1] = (g1[:-1, :-1] + g1[:-1, 1:] + g2[:-1, :-1] + g2[1:, :-1]) // 4
        d3[2::2, 2::2, 1] = (g1[:-1, 1:] + g1[1:, 1:] + g2[1:, :-1] + g2[1:, 1:]) // 4
        
        d3[1::2, 1::2, 2] = b
        d3[1::2, 2::2, 2] = (b[:, :-1] + b[:, 1:]) // 2
        d3[2::2, 1::2, 2] = (b[:-1, :] + b[1:, :]) // 2
        d3[2::2, 2::2, 2] = (b[:-1, :-1] + b[1:, :-1] + b[:-1, 1:] + b[1:, 1:]) // 4 
        return d3

    @staticmethod
    def fast_bayer_to_rgb(d2):
        d3 = np.empty(d2.shape + (3,), dtype='ubyte')
        d3[::2, ::2, 0] = d2[::2, ::2]
        d3[::2, ::2, 1] = d2[1::2, ::2]
        d3[::2, ::2, 2] = d2[1::2, 1::2]
        d3[1::2, ::2] = d3[::2, ::2]
        d3[:, 1::2] = d3[:, ::2]
        return d3

    