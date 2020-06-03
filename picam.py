import io
import random
import picamera
import datetime
from yoctopuce.yocto_api import *
from yoctopuce.yocto_weighscale import *

import traceback
from email.header import Header
import json
import os
import shutil
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib
import time
import sys
import time

import httplib2
from apiclient.discovery import build
from apiclient.errors import HttpError
from apiclient.http import MediaFileUpload
from oauth2client.client import flow_from_clientsecrets
from oauth2client.file import Storage
from oauth2client.tools import run_flow

# Explicitly tell the underlying HTTP transport library not to retry, since
# we are handling retry logic ourselves.
httplib2.RETRIES = 1

# Maximum number of times to retry before giving up.
MAX_RETRIES = 10

# Always retry when these exceptions are raised.
RETRIABLE_EXCEPTIONS = (httplib2.HttpLib2Error, IOError)

# Always retry when an apiclient.errors.HttpError with one of these status
# codes is raised.
RETRIABLE_STATUS_CODES = [500, 502, 503, 504]

# The CLIENT_SECRETS_FILE variable specifies the name of a file that contains
# the OAuth 2.0 information for this application, including its client_id and
# client_secret. You can acquire an OAuth 2.0 client ID and client secret from
# the Google API Console at
# https://console.developers.google.com/.
# Please ensure that you have enabled the YouTube Data API for your project.
# For more information about using OAuth2 to access the YouTube Data API, see:
#   https://developers.google.com/youtube/v3/guides/authentication
# For more information about the client_secrets.json file format, see:
#   https://developers.google.com/api-client-library/python/guide/aaa_client_secrets
CLIENT_SECRETS_FILE = "client_secrets.json"

# This OAuth 2.0 access scope allows an application to upload files to the
# authenticated user's YouTube channel, but doesn't allow other types of access.
YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"

# This variable defines a message to display if the CLIENT_SECRETS_FILE is
# missing.
MISSING_CLIENT_SECRETS_MESSAGE = """
WARNING: Please configure OAuth 2.0

To make this sample run you will need to populate the client_secrets.json file
found at:

   %s

with information from the API Console
https://console.developers.google.com/

For more information about the client_secrets.json file format, please visit:
https://developers.google.com/api-client-library/python/guide/aaa_client_secrets
""" % os.path.abspath(os.path.join(os.path.dirname(__file__),
                                   CLIENT_SECRETS_FILE))

VALID_PRIVACY_STATUSES = ("public", "private", "unlisted")


SMTP_HOST = "mail.abc.ef"
SMTP_PORT = 587
SMTP_USER = "username"
SMTP_PASS = "passw0rd"

MAIL_SENDER = "james@bond.com"
MAIL_DEST = "dr@no.com"


def get_authenticated_service():
    flow = flow_from_clientsecrets(CLIENT_SECRETS_FILE,
                                   scope=YOUTUBE_UPLOAD_SCOPE,
                                   message=MISSING_CLIENT_SECRETS_MESSAGE)

    storage = Storage("upload_video.py-oauth2.json")
    credentials = storage.get()

    if credentials is None or credentials.invalid:
        credentials = run_flow(flow, storage)

    return build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION,
                 http=credentials.authorize(httplib2.Http()))


def upload_video(file, title, description="description"):
    tags = None

    body = dict(
        snippet=dict(
            title=title,
            description=description,
            tags="",
            categoryId=22
        ),
        status=dict(
            privacyStatus=VALID_PRIVACY_STATUSES[0]
        )
    )
    youtube = get_authenticated_service()
    # Call the API's videos.insert method to create and upload the video.
    insert_request = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        # The chunksize parameter specifies the size of each chunk of data, in
        # bytes, that will be uploaded at a time. Set a higher value for
        # reliable connections as fewer chunks lead to faster uploads. Set a lower
        # value for better recovery on less reliable connections.
        #
        # Setting "chunksize" equal to -1 in the code below means that the entire
        # file will be uploaded in a single HTTP request. (If the upload fails,
        # it will still be retried where it left off.) This is usually a best
        # practice, but if you're using Python older than 2.6 or if you're
        # running on App Engine, you should set the chunksize to something like
        # 1024 * 1024 (1 megabyte).
        media_body=MediaFileUpload(file, chunksize=-1, resumable=True)
    )

    url = resumable_upload(insert_request)
    return url


# This method implements an exponential backoff strategy to resume a
# failed upload.
def resumable_upload(insert_request):
    response = None
    error = None
    retry = 0
    while response is None:
        try:
            print("Uploading file...")
            status, response = insert_request.next_chunk()
            if response is not None:
                if 'id' in response:
                    print("Video id '%s' was successfully uploaded." % response['id'])
                    return "https://youtu.be/%s" % response['id']
                else:
                    exit("The upload failed with an unexpected response: %s" % response)
        except HttpError as e:
            if e.resp.status in RETRIABLE_STATUS_CODES:
                error = "A retriable HTTP error %d occurred:\n%s" % (e.resp.status,
                                                                     e.content)
            else:
                raise
        except RETRIABLE_EXCEPTIONS as e:
            error = "A retriable error occurred: %s" % e

        if error is not None:
            print(error)
            retry += 1
            if retry > MAX_RETRIES:
                exit("No longer attempting to retry.")
            max_sleep = 2 ** retry
            sleep_seconds = random.random() * max_sleep
            print("Sleeping %f seconds and then retrying..." % sleep_seconds)
            time.sleep(sleep_seconds)


def sendMail(strFrom, strTo, subject, text, html):
    """ subject and text must be utf-8 string
    """
    msgRoot = MIMEMultipart('related')
    msgRoot['Subject'] = Header(subject, 'utf-8')
    msgRoot['From'] = strFrom
    msgRoot['To'] = strTo
    msgRoot.preamble = 'This is a multi-part message in MIME format.'
    # Encapsulate the plain and HTML versions of the message body in an
    # 'alternative' part, so message agents can decide which they want to display.
    msgAlternative = MIMEMultipart(html)
    msgRoot.attach(msgAlternative)
    msgText = MIMEText(text, _charset='utf-8')
    msgAlternative.attach(msgText)

    mailServer = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
    mailServer.ehlo()
    mailServer.starttls()
    mailServer.ehlo()
    msg_content = msgRoot.as_string().encode('ascii')
    mailServer.login(SMTP_USER, SMTP_PASS)
    try:
        mailServer.sendmail(strFrom, strTo, msg_content)
        mailServer.close()
    except smtplib.SMTPDataError as ignore:
        timestr = datetime.datetime.now().strftime("%y-%m-%d_%H:%M:%S")
        filename = 'mail_rejected_%s.txt' % timestr
        f = open(filename, 'w+b')
        f.write(msg_content)
        f.close()
        mailServer.close()
        print("Unable to send email (content saved in %s)" % filename)


def success(filename):
    url = upload_video(filename, "Camera trap of "+datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
    #url = ftpupload(filename)
    utf8_text = "new video: "+ url+"\n"
    sendMail(MAIL_DEST, MAIL_SENDER, "new video", utf8_text,
                          'alternative')
    os.unlink(filename)

def write_video(stream, output):
    # Write the entire content of the circular buffer to disk. No need to
    # lock the stream here as we're definitely not writing to it
    # simultaneously
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


def picam():
    # Setup the Yoctopuce API to use local USB devices
    errmsg = YRefParam()
    if YAPI.RegisterHub("usb", errmsg) != YAPI.SUCCESS:
        sys.exit("init error" + errmsg.value)

    # retreive the first WeighScale sensor
    sensor = YWeighScale.FirstWeighScale()
    if sensor is None:
        die('No Yocto-Bridge connected on USB')

    # On startup, enable excitation and tare weigh scale
    print("Taring scale...");
    sensor.set_excitation(YWeighScale.EXCITATION_AC);
    YAPI.Sleep(3000);
    sensor.tare();
    unit = sensor.get_unit();
    if not os.path.isdir("videos"):
        os.mkdir("videos")
    print("Ready!");

    with picamera.PiCamera() as camera:
        camera.resolution = (1280, 720)
        # main stream to record in continous before we detect anything on the scale
        main_stream = picamera.PiCameraCircularIO(camera, seconds=5)
        camera.start_recording(main_stream, format='h264')
        try:
            while sensor.isOnline():
                weight = sensor.get_currentValue()
                if weight > 5:
                    print("Object on the scale");
                    starttime = datetime.datetime.now().strftime("%Y-%m-%d_%H.%M.%S")
                    filename = 'videos/%s.large.h264' % starttime
                    video_file = open(filename , mode='wb')

                    # alocate two stream to record in continus
                    streamA = picamera.PiCameraCircularIO(camera, seconds=10)
                    streamB = picamera.PiCameraCircularIO(camera, seconds=10)
                    # switch to stream A
                    camera.split_recording(streamA)
                    cur_stream = 'A'
                    # save previous 10 second on file
                    write_video(main_stream, video_file)
                    # capture until scale is empty or at max 60 seconds
                    count = 0
                    while weight > 4 and count < 12:
                        # recorde max 5 seconds
                        j = 0
                        while weight > 4 and j < 5:
                            weight = sensor.get_currentValue()
                            prefix = datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")
                            recmsg = "%s weight=%d%s" % (prefix,weight, unit)
                            camera.annotate_text = recmsg
                            print(recmsg)
                            camera.wait_recording(1)
                            YAPI.HandleEvents()
                            j += 1
                        # then switch to the alternate stream
                        if cur_stream=='A':
                            camera.split_recording(streamB)
                            write_video(streamA, video_file)
                            cur_stream = 'B'
                        else:
                            camera.split_recording(streamA)
                            write_video(streamB, video_file)
                            cur_stream = 'A'
                        count += 1
                    # switch back to main stream
                    camera.split_recording(main_stream)
                    # and flush remaining data on the video file
                    if cur_stream=='A':
                        write_video(streamA, video_file)
                    else:
                        write_video(streamB, video_file)
                    video_file.close()
                    print("Video saved on file " + filename)
                    # upload the video on Youtube
                    success(filename)
                else:
                    camera.wait_recording(0.5)
                    YAPI.HandleEvents()
        finally:
            camera.stop_recording()

    YAPI.FreeAPI()

if __name__ == '__main__':
    picam()