"""
https://github.com/JohnDMcMaster/uvscada/tree/master/scopetek
https://github.com/walac/pyusb/blob/master/docs/tutorial.rst



"""
import sys
import usb.core
import pyqtgraph as pg
import numpy as np


dev = usb.core.find(idVendor=0x547)
if dev is None:
    print "No cameras found!"
    sys.exit(-1)

cfg = dev[0]
iface = cfg[(0,0)]
ep = iface[0]


permission_error_msg = """Permission denied to access camera.

To fix this on Linux:
1. Edit /etc/udev/rules.d/50-scopetek.rules, add the following (you may need to choose a different group):
     SUBSYSTEMS=="usb", ATTRS{idVendor}=="0547", GROUP="plugdev", MODE="0666"
2. Restart udev:
     sudo udevadm control --reload
3. Unplug/replug the device and try again.
"""

try:
    cfg.set()
except usb.core.USBError as err:
    if err.errno == 13:
        print permission_error_msg
        sys.exit(-1)



# basic setup for 640x480
setup = [
    (0x40, 180, 0xc8 , 0   , 10,  0           ),   # set resolution
    (0x40, 179, 0    , 0   , 10,  0           ),   # queue next frame?
    (0x40, 183, 0x19 , 0x6 , 0 ,  0           ),
    (0xc0, 182, 0    , 0x11, 10,  b'\x24\x03' ),
    (0x40, 181, 0xa1 , 0   , 10,  0           ),   # set normal/fast frame speed mode
    (0x40, 183, 0x28 , 0x35, 10,  0           ),   
    (0x40, 183, 0x34 , 0x9 , 10,  0           ),
    (0x40, 181, 0xa0 , 0   , 10,  0           ),
    (0x40, 183, 0x10 , 0x35, 10,  0           ),   # set gain
    (0x40, 183, 0xbf7, 0x9 , 10,  0           ),   # set exposure
]
for ct in setup:
    if ct[0] & 0x80 > 0:
        dev.ctrl_transfer(bmRequestType=ct[0], bRequest=ct[1], wValue=ct[2], wIndex=ct[3], data_or_wLength=ct[5])
        print ct
    else:
        result = dev.ctrl_transfer(bmRequestType=ct[0], bRequest=ct[1], wValue=ct[2], wIndex=ct[3])
        print ct, '==>', result


imv = pg.image()

def showframe():
    global ep, imv
    # read one frame
    rawdata = ep.read(640*480 + 512)
    dev.ctrl_transfer(bmRequestType=0x40, bRequest=179, wValue=0, wIndex=0)
    
    # Colors are in bayer filter pattern:
    #   RGRGRG
    #   GBGBGB
    #   RGRGRG
    #   GBGBGB
    d1 = np.array(rawdata)
    d2 = d1[512:].reshape(480, 640)
    #imv.setImage(d2.T)
    # convert to RGB
    d3 = np.empty((480, 640, 3), dtype='ubyte')
    d3[::2, ::2, 0] = d2[::2, ::2]
    d3[::2, ::2, 1] = d2[1::2, ::2]
    d3[::2, ::2, 2] = d2[1::2, 1::2]
    d3[1::2, ::2] = d3[::2, ::2]
    d3[:, 1::2] = d3[:, ::2]
    imv.setImage(d3.transpose(1, 0, 2))

def stop():
    global dev
    dev.ctrl_transfer(bmRequestType=0x40, bRequest=187, wValue=0, wIndex=0)

    
while True:
    showframe()
    pg.QtGui.QApplication.processEvents()
    if not imv.isVisible():
        # stop camera
        stop()
        break

#showframe()
