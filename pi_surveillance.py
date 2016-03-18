# -*- coding: utf-8 -*-
__author__ = 'Ryan'

from pyimagesearch.tempimage import TempImage
from dropbox.client import DropboxOAuth2FlowNoRedirect
from dropbox import Dropbox
import argparse
import warnings
import datetime
import imutils
import json
import time
import cv2

# 构建argument parser 并解析参数
ap = argparse.ArgumentParser()
ap.add_argument("-c", "--conf", required=True, help="path to the JSON configuration file")
args = vars(ap.parse_args())

# 过滤警告，加载配置文件并且初始化Dropbox
# 客户端
warnings.filterwarnings("ignore")
conf = json.load(open(args["conf"]))
client = None

avg = None
lastUploaded = datetime.datetime.now()
motionCounter = 0

def deal_frame(s_frame, dropbox_client, pi_raw_capture):
    timestamp = datetime.datetime.now()
    text = "Unoccupied"

    # 调整尺寸，转换成灰阶图像并进行模糊
    s_frame = imutils.resize(s_frame, width=500)
    gray = cv2.cvtColor(s_frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (21,21), 0)

    cv2.imshow("Gray Feed", gray)

    global avg
    if avg is None:
        print "[INFO] starting background model..."
        avg = gray.copy().astype("float")
        if pi_raw_capture is not None:
            pi_raw_capture.truncate(0)
        return

    # accumulate the weighted average between the current frame and
    # previous frames, then compute the difference between the current
    # frame and running average
    cv2.accumulateWeighted(gray, avg, 0.5)
    framedelta = cv2.absdiff(gray, cv2.convertScaleAbs(avg))

    cv2.imshow("framedelta Feed", framedelta)

    # 对图像进行阀值化，膨胀阀值图像来填补孔洞，在阀值图像上找到轮廓线
    thresh = cv2.threshold(framedelta, conf["delta_thresh"], 255, cv2.THRESH_BINARY)[1]
    thresh = cv2.dilate(thresh, None, iterations=2)
    (cnts, _) = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    cv2.imshow("thresh Feed", thresh)

    # 遍历轮廓线
    for c in cnts:
        # if the contour is too small, ignore it
        if cv2.contourArea(c) < conf["min_area"]:
            continue

        # 计算轮廓线外框，在当前帧上画出外框，并更新文本
        (x,y,w,h) = cv2.boundingRect(c)
        cv2.rectangle(s_frame, (x,y), (x + w, y + h), (0, 255, 0), 2)
        text = "Occupied"

    # 在当前帧上标文本和时间戳
    ts = timestamp.strftime("%A %d %B %Y %I:%M:%S%p")
    cv2.putText(s_frame, "Room Status: {}".format(text), (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
    cv2.putText(s_frame, ts, (10, s_frame.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 255), 1)

    # 检查房间是否被占用
    if text == "Occupied":
        # 判断上传时间间隔是否已经达到
        global  lastUploaded
        if ( timestamp - lastUploaded).seconds >= conf["min_upload_seconds"]:
            # 运动检测计数器递增
            global motionCounter
            motionCounter += 1

            # 判断包含连续运动的帧数是否已经足够多
            if motionCounter >= conf["min_motion_frames"]:
                # Write the image to the temporary file
                t = TempImage()
                cv2.imwrite(t.path, s_frame)

                # 判断dropbox是否启用
                if dropbox_client is not None:
                    # 将图像上传到dropbox并删除临时图片
                    print "[UPLOAD] {}".format(ts)
                    path = "{base_path}/{timestamp}.jpg".format(base_path=conf["dropbox_base_path"], timestamp=ts)
                    dropbox_client.put_file(path, open(t.path, "rb"))
                    t.cleanup()

                # 更新最近一次上传事件，重置计数器
                lastUploaded = datetime.datetime.now()
                motionCounter = 0
        else:
            motionCounter = 0

    # 判断安保视频是否需要显示在屏幕上
    if conf["show_video"]:
        # 显示视频
        cv2.imshow("Security Feed", s_frame)


if conf["use_dropbox"]:
    # 连接dropbox并且启动会话授权过程
    flow = DropboxOAuth2FlowNoRedirect(conf["dropbox_key"], conf["dropbox_secret"])
    print "[INFO] Authorize this application: {}".format(flow.start())
    authCode = raw_input("Enter auth code here:").strip()

    # 完成会话授权并获取客户端
    (accessToken, userID) = flow.finish(authCode)
    client = Dropbox(accessToken)
    print "[SUCCESS] dropbox account linked"

if conf["use_pi"]:
    from picamera.array import PiRGBArray
    from picamera import PiCamera

    # 初始化摄像头，并获取一个指向原始数据的引用
    camera = PiCamera()
    camera.resolution = tuple(conf["resolution"])
    camera.framerate = conf["fps"]
    rawCapture = PiRGBArray(camera, size=tuple(conf["resolution"]))

    # 等待摄像头模块启动，随后初始化平均帧，最后，上传时间戳，以及运动帧数计数器
    print "[INFO] warming up..."
    time.sleep(conf["camera_warm_up_time"])

    # 从摄像头逐帧捕获图像
    for f in camera.capture_continuous(rawCapture, format="bgr", use_video_port=True):
        # 抓取原始Numpy数组来表示图像并初始化时间戳以及occupied/unoccupied文本
        frame = f.array
        deal_frame(frame, client, rawCapture)


        # 退出控制
        key = cv2.waitKey(1)
        if key == ord("q"):
            break

        # 清理数据流为下一帧做准备
        rawCapture.truncate(0)
else:
    time.sleep(conf["camera_warmup_time"])

    camera = cv2.VideoCapture(0)
    while True:
        (_, frame) = camera.read()
        deal_frame(frame, None, None)

        # 退出控制
        key = cv2.waitKey(1)
        if key == ord("q"):
            break
