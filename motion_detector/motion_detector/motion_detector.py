#!/usr/bin/env python3


import cv2 as cv
import numpy as np
from time import time
from torch.cuda import is_available as cuda_is_available

import rclpy
from rclpy.node import Node
from cv_bridge import CvBridge

from nav_msgs.msg import Odometry
from sensor_msgs.msg import Image
from dynamic_nav_msgs.msg import YoloData

from .submodules.yolo import Yolo
from .submodules.yolo_classes import classes_list


class MotionDetector(Node):

    def __init__(self):
        super().__init__('motion_detector')
        self.declare_parameters(namespace='', parameters=[('input_topic', ''),
                                                          ('output_topic', ''),
                                                          ('create_mask', True),
                                                          ('gpu_yolo_model', ''),
                                                          ('cpu_yolo_model', '')])
        self.input_topic_ = self.get_parameter('input_topic').value
        self.output_topic_ = self.get_parameter('output_topic').value
        self.create_mask_ = self.get_parameter('create_mask').value
        self.get_logger().info(f'input_topic: {self.input_topic_}')
        self.get_logger().info(f'output_topic: {self.output_topic_}')
        self.get_logger().info(f'create mask: {self.create_mask_}')
        self.subscription_ = self.create_subscription(YoloData, self.get_parameter('input_topic').value, self.callback, 1)
        self.subscription_  # prevent unused variable warning
        self.publisher_ = self.create_publisher(YoloData, self.get_parameter('output_topic').value, 10)
        self.bridge_ = CvBridge()
        yolo_model_type_ = self.get_parameter('gpu_yolo_model').value if cuda_is_available() else self.get_parameter('cpu_yolo_model').value
        self.model_ = Yolo(yolo_model=yolo_model_type_, classes=classes_list)
        self.h, self.w = (480, 640)
        self.model_.run(np.zeros((self.h, self.w, 3), dtype='uint8'))
        self.empty_mask_ = np.zeros((self.h, self.w, 1), dtype='uint8')
        self.get_logger().info('model initialized')

    def get_boxes_coordinates(self, boxes):
        x = []
        for box in boxes:
            for v in box.xyxy.tolist()[0]:
                x.append(int(v))
        return x

    def callback(self, msg):
        t = time()
        cv_frame = self.bridge_.imgmsg_to_cv2(msg.rgb, desired_encoding='passthrough')
        boxes = []

        # 0ms

        output = self.model_.run(cv_frame)

        # 35ms

        success, mask = self.model_.merge_masks(output.masks)
        if not success or not self.create_mask_:
            msg.mask = self.bridge_.cv2_to_imgmsg(self.empty_mask_, encoding='passthrough')
        else:
            if self.model_.gpu:
                mask = mask[(self.w-self.h)//2:self.h+(self.w-self.h)//2, :]
            mask = cv.normalize(mask, None, 255, 0, cv.NORM_MINMAX, cv.CV_8U)
            boxes = self.get_boxes_coordinates(output.boxes)
            msg.mask = self.bridge_.cv2_to_imgmsg(mask, encoding='passthrough')
            msg.boxes = boxes

        # cv_frame = cv.resize(cv_frame, (320, 240), interpolation=cv.INTER_LINEAR)
        # mask = cv.resize(mask, (320, 240), interpolation=cv.INTER_LINEAR)
        # depth = cv.resize(self.bridge_.imgmsg_to_cv2(msg.depth, desired_encoding='passthrough'), (320, 240), interpolation=cv.INTER_LINEAR)

        # msg.rgb = self.bridge_.cv2_to_imgmsg(cv_frame, encoding='passthrough')
        # msg.mask = self.bridge_.cv2_to_imgmsg(mask, encoding='passthrough')
        # msg.depth = self.bridge_.cv2_to_imgmsg(depth, encoding='passthrough')

        self.publisher_.publish(msg)

        # cv.imshow('main_mask', mask)
        # cv.imshow('frame', cv_frame)
        # cv.imshow('depth', depth)
        # cv.imshow('depth_masked', depth_masked)
        # cv.waitKey(1)

        self.get_logger().info(f'dt = {int((time() - t) * 1000)}ms')


def main(args=None):
    rclpy.init(args=args)
    motion_detector = MotionDetector()
    rclpy.spin(motion_detector)
    motion_detector.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
