"""
https://github.com/JohnDMcMaster/uvscada/tree/master/scopetek
https://github.com/walac/pyusb/blob/master/docs/tutorial.rst



"""
import sys
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
                
        self.resolution = resolution
        self.fast = fast
        self.exposure = exposure
        self.gain = gain

    def stop(self):
        self.dev.ctrl_transfer(bmRequestType=0x40, bRequest=187, wValue=0, wIndex=0)

    def readframe(self):
        """Read one frame from the video stream.
        
        # Colors are in bayer filter pattern:
        #   RGRGRG
        #   GBGBGB
        #   RGRGRG
        #   GBGBGB
        """
        # read one frame
        extra = 256 if self.resolution[0] == 2592 else 512
        data = self.ep.read(self.resolution[0] * self.resolution[1] + extra)
        
        # queue the next frame
        self.dev.ctrl_transfer(bmRequestType=0x40, bRequest=179, wValue=0, wIndex=0)
        
        d1 = np.array(data)
        d2 = d1[extra:].reshape(self.resolution[1], self.resolution[0])
        return d2
    
    @staticmethod
    def bayer_to_rgb(d2):
        d3 = np.empty(d2.shape + (3,), dtype='ubyte')
        d3[::2, ::2, 0] = d2[::2, ::2]
        d3[::2, ::2, 1] = d2[1::2, ::2]
        d3[::2, ::2, 2] = d2[1::2, 1::2]
        d3[1::2, ::2] = d3[::2, ::2]
        d3[:, 1::2] = d3[:, ::2]
        return d3

