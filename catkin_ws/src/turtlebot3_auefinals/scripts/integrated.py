#!/usr/bin/env python
import rospy
import cv2
import numpy as np
from cv_bridge import CvBridge, CvBridgeError
from geometry_msgs.msg import Twist
from sensor_msgs.msg import Image
from move_robot import MoveTurtlebot3
from geometry_msgs.msg import Twist, PoseArray
from sensor_msgs.msg import LaserScan
from darknet_ros_msgs.msg import BoundingBoxes
from std_msgs.msg import String
from nav_msgs.msg import Odometry
from people_msgs.msg import PositionMeasurementArray
import tf
import math
from math import sqrt
import time

right = 0.0
left = 0.0
uk1s = 0.0
er_1s = 0.0
er_2s = 0.0
errors = 0.0
count = 0
kps_t = 0.4
kds_t = 0.0004
kis_t = 0.0015
uk1s_t = 0.0
er_1s_t = 0.0
er_2s_t = 0.0
tb_x_trans = 0.0
tb_y_trans = 0.0
tb_z_trans = 0.0
tb_x_or = 0.0
tb_y_or = 0.0 
tb_z_or = 0.0
tb_w_or = 0.0
man_x = 0.0
man_y = 0.0
man_z = 0.0
line_following_mode = False
finding_lane = True
stop_sign_found = False
person_tracker = False
maninrange = False
ctr = 0

class LineFollower(object):

    def __init__(self):
    
        self.bridge_object = CvBridge()
        self.image_sub = rospy.Subscriber("/camera/rgb/image_raw",Image,self.camera_callback)
        self.tb_sub = rospy.Subscriber('/odom',Odometry,self.pose_callback)
        self.manforce = rospy.Subscriber('/people_tracker_measurements', PositionMeasurementArray, self.man_callback)
        self.moveTurtlebot3_object = MoveTurtlebot3()
        self.wall_following_sub = rospy.Subscriber('scan', LaserScan, self.wall_following_callback)
        self.stop_sign_sub = rospy.Subscriber("/darknet_ros/bounding_boxes", BoundingBoxes, self.detection_callback)
        
    def pose_callback(self, odom1_msg):
        global tb_x_trans,tb_y_trans,tb_z_trans,tb_x_or,tb_y_or,tb_z_or,tb_w_or
        tb_x_trans = odom1_msg.pose.pose.position.x
        tb_y_trans = odom1_msg.pose.pose.position.y
        tb_z_trans = odom1_msg.pose.pose.position.z
        tb_x_or = odom1_msg.pose.pose.orientation.x
        tb_y_or = odom1_msg.pose.pose.orientation.y
        tb_z_or = odom1_msg.pose.pose.orientation.z
        tb_w_or = odom1_msg.pose.pose.orientation.w

    def man_callback(self,data1):
        global man_x,man_y,man_z,maninrange
        if len(data1.people)!=0:
            maninrange = True
            man_x = data1.people[0].pos.x
            man_y = data1.people[0].pos.y
            man_z = data1.people[0].pos.z 
        else:
            maninrange = False

    def wall_following_callback(self,points):
        global right, left
        frontleft = points.ranges[20:80]
        frontright = points.ranges[300:339]
        left = []
        right = []
        for i in frontleft:
            if 0 < i < 10:
                left.append(i)
        for j in frontright:
            if 0 < j < 10:
                right.append(j)
        right = np.mean(right)
        left = np.mean(left)
        return left, right

    def detection_callback(self,msg):
        global stop_sign_found
        for x in range(len(msg.bounding_boxes)):
            if msg.bounding_boxes[x].Class == "stop sign" and stop_sign_found == False:
                stop_sign_found = True

    def camera_callback(self,data):
        
        try:
            # We select bgr8 because its the OpneCV encoding by default
	        cv_image = self.bridge_object.imgmsg_to_cv2(data, desired_encoding="bgr8")
        except CvBridgeError as e:
            rospy.loginfo(e)
        # velocity_publisher = rospy.Publisher("/cmd_vel",Twist,queue_size=10)  
        twist_object = Twist()
        # We get image dimensions and crop the parts of the image we dont need
        height, width, channels = cv_image.shape
        crop_img = cv_image[(height)/2+120:height][1:width]
        
        # Convert from RGB to HSV
        hsv = cv2.cvtColor(crop_img, cv2.COLOR_BGR2HSV)
        
        # Define the Yellow Colour in HSV

        """
        To know which color to track in HSV use ColorZilla to get the color registered by the camera in BGR and convert to HSV. 
        """

        # Threshold the HSV image to get only yellow colors
        lower_yellow = np.array([20,100,100])
        upper_yellow = np.array([50,255,255])
        mask = cv2.inRange(hsv, lower_yellow, upper_yellow)
        
        # Calculate centroid of the blob of binary image using ImageMoments
       
        global line_following_mode

        m = cv2.moments(mask, False)

        try:
            cx, cy = m['m10']/m['m00'], m['m01']/m['m00']
            line_following_mode = True
            finding_lane = False
            person_tracker = True
        except ZeroDivisionError:
            cx, cy = height/2, width/2
            finding_lane = True
            line_following_mode = False
            person_tracker = True

        res = cv2.bitwise_and(crop_img,crop_img, mask= mask)

        cv2.circle(res,(int(cx), int(cy)), 10,(0,0,255),-1)

        # cv2.imshow("Original", cv_image)
        #cv2.imshow("MASK", mask)
        
        global errors, uks, uk1s, er_1s, er_2s, ctr

        if finding_lane and ctr == 0:
            rospy.loginfo("FINDING LINE")
            #if not line_following_mode:
            kps = 1.1
            kds = 0.00065
            kis = 0.05

            errors = right - left
            k_1s = kps + kis + kds
            k_2s = -kps - (2.0 * kds)
            k_3s = kds

            uks = uk1s + (k_1s * errors) + (k_2s * er_1s) + (k_3s * er_2s)
            uks = uks
            uk1s = uks
            er_2s = er_1s
            er_1s = errors

            twist_object.linear.x = 0.1
            if errors == 0:
                twist_object.angular.z = 0.0
            else:
                twist_object.angular.z = -uks
            self.moveTurtlebot3_object.move_robot(twist_object)
            # velocity_publisher.publish(twist_object)

        if line_following_mode:
            rospy.loginfo("FOLLOWING LINE")
            cv2.imshow("RES", res)
            cv2.waitKey(1)
            error_x = cx - (height / 2) - 89
            twist_object.linear.x = 0.1
            twist_object.angular.z = -error_x / 950
            # velocity_publisher.publish(twist_object)
            self.moveTurtlebot3_object.move_robot(twist_object)
            rospy.loginfo("ANGULAR VALUE SENT===>"+str(twist_object.angular.z))

            global count
            if stop_sign_found:
                count = count + 1
                rospy.loginfo(count)
                if count == 108:
                    t = rospy.get_time()
                    T = t
                    rospy.loginfo(count)
                    while T <= t + 3:
                        rospy.loginfo("STOP SIGN FOUND")
                        twist_object.linear.x = 0
                        twist_object.angular.z = 0
                        # velocity_publisher.publish(twist_object)
                        self.moveTurtlebot3_object.move_robot(twist_object)
                        rospy.loginfo("STOPPED")
                        T = rospy.get_time()
                    ctr += 1
                if count >= 111:
                    line_following_mode = False
            
        if person_tracker==True and ctr == 1:

            rospy.loginfo("PERSON TRACKING MODE")
            global kps_t, kds_t, kis_t, uk1s_t, er_1s_t, er_2s_t
            quaternion = (
            tb_x_or,
            tb_y_or,
            tb_z_or,
            tb_w_or)

            #convert the quaternion to roll-pitch-yaw
            rpy_tb = tf.transformations.euler_from_quaternion(quaternion)
            roll_tb = rpy_tb[0]
            pitch_tb = rpy_tb[1]
            yaw_tb = rpy_tb[2]
            velocity_publisher = rospy.Publisher("/cmd_vel",Twist,queue_size=10)
            velocity_publisher = rospy.Publisher('/cmd_vel',Twist,queue_size = 10)
            vel_msg = Twist()
            if maninrange is True:
                
                distance = sqrt((tb_x_trans - man_x)**2 + (tb_y_trans-man_y)**2)
                error_x = distance - 0.5
                distance_angular = (math.atan2(man_y-tb_y_trans,man_x-tb_x_trans))-yaw_tb
                error_z = distance_angular

                # rospy.loginfo(error_x)
                k_1s_t = kps_t + kis_t + kds_t
                k_2s_t = -kps_t - (2.0 * kds_t)
                k_3s_t = kds_t

                uks_t = uk1s_t + (k_1s_t * error_x) + (k_2s_t * er_1s_t) + (k_3s_t * er_2s_t)
                uks_t = uks_t
                uk1s_t = uks_t
                er_2s_t = er_1s_t
                er_1s_t = error_x

                if error_x>0.005:
                    vel_msg.linear.x = uks_t*0.7
                    # print("positive x vel",vel_msg.linear.x)
                elif error_x<=0.002:
                    vel_msg.linear.x = uks_t*0.2
                    # print("negative x vel",vel_msg.linear.x)
                elif 0.002<error_x<=0.005:
                    vel_msg.linear.x = 0.0
                    # rospy.loginfo("xstop")
                if error_z>-0.7:
                    vel_msg.angular.z = error_z*0.6
                    # print("z_vel", vel_msg.angular.z)
                else:
                    vel_msg.angular.z = 0
                    # print("zstop")
            else:
                rospy.loginfo("Too far, moving closer")
                vel_msg.linear.x = 0.02
                vel_msg.angular.z = 0
            velocity_publisher.publish(vel_msg)
                # self.moveTurtlebot3_object.move_robot(twist_object)
           
            # rospy.Subscriber('/people_tracker_measurements', PositionMeasurementArray, man_callback)   
        # Make it start turning
        # self.moveTurtlebot3_object.move_robot(twist_object)
        
    def clean_up(self):
        # self.moveTurtlebot3_object.clean_class()
        cv2.destroyAllWindows()
        
        

def main():
    rospy.init_node('line_following_node', anonymous=True)
    
    
    line_follower_object = LineFollower()
    
    rate = rospy.Rate(1)
    ctrl_c = False
    def shutdownhook():
        # works better than the rospy.is_shut_down()
        # line_follower_object.clean_up()
        rospy.loginfo("shutdown time!")
        ctrl_c = True
    
    rospy.on_shutdown(shutdownhook)
    
    while not ctrl_c:
        rate.sleep()

    
    
if __name__ == '__main__':
    main()
