import io
import random
import picamera
import datetime
from yoctopuce.yocto_api import *
from yoctopuce.yocto_weighscale import *




def write_video(stream, starttime):
    # Write the entire content of the circular buffer to disk. No need to
    # lock the stream here as we're definitely not writing to it
    # simultaneously
    with io.open('videos/%s.before.h264' % starttime, 'wb') as output:
        for frame in stream.frames:
            if frame.frame_type == picamera.PiVideoFrameType.sps_header:
                stream.seek(frame.position)
                break
        while True:
            buf = stream.read1()
            if not buf:
                break
            output.write(buf)
    # Wipe the circular stream once we're done
    stream.seek(0)
    stream.truncate()




errmsg = YRefParam()

# Setup the API to use local USB devices
if YAPI.RegisterHub("usb", errmsg) != YAPI.SUCCESS:
    sys.exit("init error" + errmsg.value)

# retreive any genericSensor sensor
sensor = YWeighScale.FirstWeighScale()
if sensor is None:
    die('No Yocto-Bridge connected on USB')

# On startup, enable excitation and tare weigh scale
print("Taring scale...");
sensor.set_excitation(YWeighScale.EXCITATION_AC);
YAPI.Sleep(3000);
sensor.tare();
unit = sensor.get_unit();

print("Ready!");

with picamera.PiCamera() as camera:
    camera.resolution = (1280, 720)
    stream = picamera.PiCameraCircularIO(camera, seconds=10)
    camera.start_recording(stream, format='h264')
    try:
        while sensor.isOnline():
            weight = sensor.get_currentValue()
            if weight > 5:
                print("Object on the scale take a 5s video of it");
                starttime = datetime.datetime.now().strftime("%Y-%m-%d_%H.%M.%S")
                # As soon as we detect motion, split the recording to
                # record the frames "after" motion
                camera.split_recording('videos/%s.after.h264' % starttime)
                # Write the 10 seconds "before" motion to disk as well
                write_video(stream, starttime)
                log_file = "videos/" + starttime + ".txt"
                count = 0
                while weight > 5 and count < 300:
                    weight = sensor.get_currentValue()
                    prefix = datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")
                    recmsg = "%s weight=%d%s" % (prefix,weight, unit)
                    camera.annotate_text = recmsg
                    print(recmsg)
                    with open(log_file, "a") as myfile:
                        myfile.write(recmsg+"\n")
                    count += 1
                    YAPI.Sleep(1000)
                camera.wait_recording(1)
                camera.split_recording(stream)
            else:
                camera.wait_recording(1)
            YAPI.HandleEvents();
    finally:
        camera.stop_recording()

YAPI.FreeAPI()
