# -*- coding: utf-8 -*-
#
# Software License Agreement (BSD License)
#
# Copyright (c) 2010, Arizona Robotics Research Group,
# University of Arizona. All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
#  * Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
#  * Redistributions in binary form must reproduce the above
#    copyright notice, this list of conditions and the following
#    disclaimer in the documentation and/or other materials provided
#    with the distribution.
#  * Neither the name of University of Arizona nor the names of its
#    contributors may be used to endorse or promote products derived
#    from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
# Author: Antons Rebguns
#

from __future__ import division

from math import fabs
from math import fmod
from math import pi

from threading import Thread

import roslib
roslib.load_manifest('ax12_controller_core')

import rospy
import actionlib

from ax12_driver_core.ax12_const import *
from ax12_driver_core.ax12_user_commands import *
from ax12_controller_core.joint_controller import JointControllerAX12

from std_msgs.msg import Float64
from trajectory_msgs.msg import JointTrajectory
from pr2_controllers_msgs.msg import JointTrajectoryControllerState
from pr2_controllers_msgs.msg import JointTrajectoryAction
from ua_controller_msgs.msg import JointState
from ax12_driver_core.msg import MotorStateList

from pr2_controllers_msgs.srv import QueryTrajectoryState
from ax12_controller_core.srv import SetSpeed

class Spline():
    def __init__(self):
        self.coeff = [0.0] * 6

class Segment():
    def __init__(self):
        self.start_time = 0.0
        self.duration = 0.0
        self.position = 0.0
        self.velocity = None

class JointTrajectoryActionController(JointControllerAX12):
    def __init__(self, out_cb, param_path, port_name):
        self.running = False
        self.send_packet_callback = out_cb
        self.controller_namespace = param_path
        self.port_namespace = port_name[port_name.rfind('/') + 1:]

    def initialize(self):
        self.joint_names = rospy.get_param(self.controller_namespace + '/joints', [])
        self.joint_params = rospy.get_param(self.controller_namespace + '/params', [])
        self.joint_states = dict(zip(self.joint_names, [JointState(name=jn) for jn in self.joint_names]))

        self.__extract_info()
        print self.joint_params

        ns = self.controller_namespace + '/joint_trajectory_action_node/constraints'
        self.goal_time_constraint = rospy.get_param(ns + '/goal_time', 0.0)
        self.stopped_velocity_tolerance = rospy.get_param(ns + '/stopped_velocity_tolerance', 0.01)
        self.goal_constraints = []
        self.trajectory_constraints = []

        for joint in self.joint_names:
            self.goal_constraints.append(rospy.get_param(ns + '/' + joint + '/goal', -1.0))
            self.trajectory_constraints.append(rospy.get_param(ns + '/' + joint + '/trajectory', -1.0))

        # Publishers
        self.state_pub = rospy.Publisher(self.controller_namespace + '/state', JointTrajectoryControllerState)

        # Subscribers
        self.command_sub = rospy.Subscriber(self.controller_namespace + '/command', JointTrajectory, self.process_command)
        self.motor_states_sub = rospy.Subscriber('motor_states/%s' % self.port_namespace, MotorStateList, self.process_motor_states)

        # Services
        self.query_state_service = rospy.Service(self.controller_namespace + '/query_state', QueryTrajectoryState, self.process_query_state)

        seg = Segment()
        seg.start_time = 0.0
        seg.duration = 0.0
        seg.splines = [Spline() for _ in range(len(self.joint_names))]
        self.trajectory = [seg]

        self.action_server = actionlib.SimpleActionServer(self.controller_namespace + '/joint_trajectory_action',
                                                          JointTrajectoryAction,
                                                          execute_cb=self.process_trajectory_action)

        self.msg = JointTrajectoryControllerState()
        self.msg.joint_names = self.joint_names
        self.msg.desired.positions = [0.0] * len(self.joint_names)
        self.msg.desired.velocities = [0.0] * len(self.joint_names)
        self.msg.desired.accelerations = [0.0] * len(self.joint_names)
        self.msg.actual.positions = [0.0] * len(self.joint_names)
        self.msg.actual.velocities = [0.0] * len(self.joint_names)
        self.msg.error.positions = [0.0] * len(self.joint_names)
        self.msg.error.velocities = [0.0] * len(self.joint_names)
        return True

    def __extract_info(self):
        for joint in self.joint_names:
            motor_id = self.joint_params[joint]['motor']['id']
            radians_per_encoder_tick = rospy.get_param('dynamixel/%s/%d/radians_per_encoder_tick' % (self.port_namespace, motor_id))
            encoder_ticks_per_radian = rospy.get_param('dynamixel/%s/%d/encoder_ticks_per_radian' % (self.port_namespace, motor_id))
            initial_position_raw = self.joint_params[joint]['motor']['init']
            min_angle_raw = self.joint_params[joint]['motor']['min']
            max_angle_raw = self.joint_params[joint]['motor']['max']
            flipped = min_angle_raw > max_angle_raw

            self.joint_params[joint]['motor']['radians_per_encoder_tick'] = radians_per_encoder_tick
            self.joint_params[joint]['motor']['encoder_ticks_per_radian'] = encoder_ticks_per_radian
            self.joint_params[joint]['motor']['flipped'] = flipped

            flip_mult = -1 if flipped else 1
            self.joint_params[joint]['min_angle'] = flip_mult * (min_angle_raw - initial_position_raw) * radians_per_encoder_tick
            self.joint_params[joint]['max_angle'] = flip_mult * (max_angle_raw - initial_position_raw) * radians_per_encoder_tick

            encoder_resolution = rospy.get_param('dynamixel/%s/%d/encoder_resolution' % (self.port_namespace, motor_id))
            max_position = encoder_resolution - 1

            self.joint_params[joint]['motor']['encoder_resolution'] = encoder_resolution
            self.joint_params[joint]['motor']['max_position'] = max_position

    def start(self):
        self.running = True
        print 'Starting'

    def stop(self):
        self.running = False
        print 'Stopping'

    def process_command(self, msg):
        pass

    def process_motor_states(self, msg):
        if self.running:
            for joint in self.joint_names:
                motor_id = self.joint_params[joint]['motor']['id']
                initial_position_raw = self.joint_params[joint]['motor']['init']
                flipped = self.joint_params[joint]['motor']['flipped']
                radians_per_encoder_tick = self.joint_params[joint]['motor']['radians_per_encoder_tick']
                encoder_resolution = self.joint_params[joint]['motor']['encoder_resolution']

                state = filter(lambda state: state.id == motor_id, msg.motor_states)
                if state:
                    state = state[0]
                    joint_state = self.joint_states[joint]
                    joint_state.motor_ids = motor_id
                    joint_state.goal_pos = self.raw_to_rad(state.goal, initial_position_raw, flipped, radians_per_encoder_tick)
                    joint_state.current_pos = self.raw_to_rad(state.position, initial_position_raw, flipped, radians_per_encoder_tick)
                    joint_state.error = state.error * radians_per_encoder_tick
                    joint_state.velocity = (state.speed / encoder_resolution) * DMXL_MAX_SPEED_RAD
                    joint_state.load = state.load
                    joint_state.is_moving = state.moving
                    joint_state.header.stamp = rospy.Time.from_sec(state.timestamp)

    def process_query_state(self, req):
        pass

    def set_joint_speed(self, joint, speed):
        if speed < DMXL_MIN_SPEED_RAD: speed = DMXL_MIN_SPEED_RAD
        elif speed > DMXL_MAX_SPEED_RAD: speed = DMXL_MAX_SPEED_RAD
        speed_raw = int(round(speed / DMXL_SPEED_RAD_SEC_PER_TICK))
        motor_id = self.joint_params[joint]['motor']['id']
        mcv = (motor_id, speed_raw if speed_raw > 0 else 1)
        self.send_packet_callback((DMXL_SET_GOAL_SPEED, [mcv]))

    def set_joint_position(self, joint, position):
        angle = position

        motor_id = self.joint_params[joint]['motor']['id']
        initial_position_raw = self.joint_params[joint]['motor']['init']
        min_angle = self.joint_params[joint]['min_angle']
        max_angle = self.joint_params[joint]['max_angle']
        radians_per_encoder_tick = self.joint_params[joint]['motor']['radians_per_encoder_tick']
        encoder_ticks_per_radian = self.joint_params[joint]['motor']['encoder_ticks_per_radian']
        flipped = self.joint_params[joint]['motor']['flipped']

        if angle < min_angle: angle = min_angle
        elif angle > max_angle: angle = max_angle
        mcv = (motor_id, self.rad_to_raw(angle, initial_position_raw, flipped, encoder_ticks_per_radian))
        self.send_packet_callback((DMXL_SET_GOAL_POSITION, [mcv]))

    def set_joint_position_velocity(self, joint, position, velocity):
        motor_id = self.joint_params[joint]['motor']['id']
        initial_position_raw = self.joint_params[joint]['motor']['init']
        min_angle = self.joint_params[joint]['min_angle']
        max_angle = self.joint_params[joint]['max_angle']
        radians_per_encoder_tick = self.joint_params[joint]['motor']['radians_per_encoder_tick']
        encoder_ticks_per_radian = self.joint_params[joint]['motor']['encoder_ticks_per_radian']
        flipped = self.joint_params[joint]['motor']['flipped']

        if position < min_angle: position = min_angle
        elif position > max_angle: position = max_angle

        if speed < DMXL_MIN_SPEED_RAD: speed = DMXL_MIN_SPEED_RAD
        elif speed > DMXL_MAX_SPEED_RAD: speed = DMXL_MAX_SPEED_RAD
        speed_raw = int(round(speed / DMXL_SPEED_RAD_SEC_PER_TICK))

        mcv = (motor_id,
               self.rad_to_raw(position, initial_position_raw, flipped, encoder_ticks_per_radian),
               speed_raw)

        self.send_packet_callback((DMXL_SET_GOAL_POSITION, [mcv]))

    def process_trajectory_action(self, goal):
        traj = goal.trajectory

        # Ensures that the joints in the goal match the joints we are commanding.
        if set(self.joint_names) != set(traj.joint_names):
            msg = "Joints on incoming goal don't match our joints"
            rospy.logerr(msg)
            self.action_server.set_aborted(text=msg)
            return

        # Correlates the joints we're commanding to the joints in the message
        lookup = [-1] * len(self.joint_names)  # Maps from an index in joint_names to an index in the traj

        for j, joint in enumerate(self.joint_names):
            if joint not in traj.joint_names:
                msg = 'Unable to locate joint %s in the commanded trajectory.' % self.joint_names[j]
                rospy.logerr(msg)
                self.action_server.set_aborted(text=msg)
                return

            lookup[j] = traj.joint_names.index(joint)

        durations = [0.0] * len(traj.points)

        if len(traj.points) > 0:
            durations[0] = traj.points[0].time_from_start.to_sec()

        for i in range(1, len(traj.points)):
            durations[i] = (traj.points[i].time_from_start - traj.points[i-1].time_from_start).to_sec()

        if not traj.points[0].positions:
            msg = 'First point of trajectory has no positions'
            rospy.logerr(msg)
            self.action_server.set_aborted(text=msg)
            return

        trajectory = []
        time = rospy.Time.now() + rospy.Duration(0.01)
        print 'goal timestamp', traj.header.stamp.to_sec()
        print 'current time', time.to_sec()

        for i in range(len(traj.points)):
            seg = Segment()

            if traj.header.stamp == rospy.Time(0.0):
                seg.start_time = (time + traj.points[i].time_from_start).to_sec() - durations[i]
            else:
                seg.start_time = (traj.header.stamp + traj.points[i].time_from_start).to_sec() - durations[i]
                print i, traj.header.stamp.to_sec(), traj.points[i].time_from_start.to_sec(), durations[i]

            seg.duration = durations[i]

            # Checks that the incoming segment has the right number of elements.
            if len(traj.points[i].accelerations) != 0 and len(traj.points[i].accelerations) != len(self.joint_names):
                msg = 'Command point %d has %d elements for the accelerations' % (i, len(traj.points[i].accelerations))
                rospy.logerr(msg)
                self.action_server.set_aborted(text=msg)
                return

            if len(traj.points[i].velocities) != 0 and len(traj.points[i].velocities) != len(self.joint_names):
                msg = 'Command point %d has %d elements for the velocities' % (i, len(traj.points[i].velocities))
                rospy.logerr(msg)
                self.action_server.set_aborted(text=msg)
                return

            if len(traj.points[i].positions) != len(self.joint_names):
                msg = 'Command point %d has %d elements for the positions' % (i, len(traj.points[i].positions))
                rospy.logerr(msg)
                self.action_server.set_aborted(text=msg)
                return

            accelerations = [0.0] * len(traj.points[i].accelerations)
            velocities = [0.0] * len(traj.points[i].velocities)
            positions = [0.0] * len(traj.points[i].positions)

            for j in range(len(self.joint_names)):
                if len(accelerations) != 0:
                    accelerations[j] = traj.points[i].accelerations[lookup[j]]
                if len(velocities) != 0:
                    velocities[j] = traj.points[i].velocities[lookup[j]]
                    seg.velocity = velocities[j]
                if len(positions) != 0:
                    positions[j] = traj.points[i].positions[lookup[j]]
                    seg.position = positions[j]

            trajectory.append(seg)

        end_time = traj.header.stamp + rospy.Duration(sum(durations))
        rate = rospy.Rate(25)

        rospy.loginfo('Waiting for trajectory to start executing')

        while traj.header.stamp > time:
            time = rospy.Time.now()
            rate.sleep()

        rospy.loginfo('trajectory time duration is %.3lf', sum(durations))
        rospy.loginfo('starting trajectory at %.3lf, end time is %.3lf', time.to_sec(), end_time.to_sec())

        while time < end_time:
            # Determines which segment of the trajectory to use
            seg = -1
            while (seg+1 < len(trajectory) and trajectory[seg+1].start_time < time.to_sec()):
                seg += 1

            if seg == -1:
                msg = ''

                if not trajectory:
                    msg = 'No segments in the trajectory'
                    rospy.logerr(msg)
                else:
                    msg = 'No earlier segments. First segment starts at %.3lf (now = %.3lf)' % (trajectory[0].start_time, time.to_sec())
                    rospy.logerr(msg)

                self.action_server.set_aborted(text=msg)
                return

            print 'current segment is ', seg, 'time left', durations[seg] - (time.to_sec() - trajectory[seg].start_time), 'cur time', time.to_sec()

            error = [0.0] * len(self.joint_names)
            vel_error = [0.0] * len(self.joint_names)
            qd = [0.0] * len(self.joint_names)

            for i in range(len(self.joint_names)):
                cur_pos = self.joint_states[self.joint_names[i]].current_pos
                des_pos = trajectory[seg].position
                error[i] = abs(cur_pos - des_pos)
                time_left = durations[seg] - (time.to_sec() - trajectory[seg].start_time)
                qd[i] = error[i] / time_left + 0.1
                qd[i] = trajectory[seg].velocity if qd[i] > trajectory[seg].velocity else qd[i]
                self.set_joint_speed(self.joint_names[i], qd[i])
                self.set_joint_position(self.joint_names[i], des_pos)
                print i, self.joint_names[i], 'cur', cur_pos, 'des', des_pos, 'err', error[i], 'speed', qd[i]

            # Wrap up and publish current joint state
            self.msg.header.stamp = time

            for i in range(len(self.joint_names)):
                js = self.joint_states[self.joint_names[i]]
                self.msg.desired.positions[i] = trajectory[seg].position
                self.msg.desired.velocities[i] = abs(qd[i])
                self.msg.desired.accelerations[i] = 0.0
                self.msg.actual.positions[i] = js.current_pos
                self.msg.actual.velocities[i] = abs(js.velocity)
                self.msg.error.positions[i] = error[i]
                self.msg.error.velocities[i] = self.msg.actual.velocities[i] - self.msg.desired.velocities[i]

                self.state_pub.publish(self.msg)

            rate.sleep()
            time = rospy.Time.now()

        rospy.loginfo('trajectory following ended at %.3lf', rospy.Time.now().to_sec())
        self.action_server.set_succeeded()



    ################################################################################
    #------------------- Spline generating and sampling functions -----------------#
    ################################################################################

    def generate_powers(self, n, x):
        powers = [1.0]

        for i in range(1, n+1):
            powers.append(powers[i-1] * x)

        return powers

    def get_cubic_spline_coefficients(self, start_pos, start_vel, end_pos, end_vel, time):
        coefficients = [0.0] * 6

        if time == 0.0:
            coefficients[0] = end_pos
            coefficients[1] = end_vel
            coefficients[2] = 0.0
            coefficients[3] = 0.0
        else:
            T = self.generate_powers(3, time)
            coefficients[0] = start_pos
            coefficients[1] = start_vel
            coefficients[2] = (-3.0*start_pos + 3.0*end_pos - 2.0*start_vel*T[1] - end_vel*T[1]) / T[2]
            coefficients[3] = (2.0*start_pos - 2.0*end_pos + start_vel*T[1] + end_vel*T[1]) / T[3]

        return coefficients

    def get_quintic_spline_coefficients(self, start_pos, start_vel, start_acc, end_pos, end_vel, end_acc, time):
        coefficients = [0.0] * 6

        if time == 0.0:
            coefficients[0] = end_pos
            coefficients[1] = end_vel
            coefficients[2] = 0.5 * end_acc
            coefficients[3] = 0.0
            coefficients[4] = 0.0
            coefficients[5] = 0.0
        else:
            T = self.generate_powers(5, time)
            coefficients[0] = start_pos
            coefficients[1] = start_vel
            coefficients[2] = 0.5 * start_acc
            coefficients[3] = (-20.0*start_pos + 20.0*end_pos - 3.0*start_acc*T[2] + end_acc*T[2] -
                                12.0*start_vel*T[1] - 8.0*end_vel*T[1]) / (2.0*T[3])
            coefficients[4] = (30.0*start_pos - 30.0*end_pos + 3.0*start_acc*T[2] - 2.0*end_acc*T[2] +
                                16.0*start_vel*T[1] + 14.0*end_vel*T[1]) / (2.0*T[4])
            coefficients[5] = (-12.0*start_pos + 12.0*end_pos - start_acc*T[2] + end_acc*T[2] -
                                6.0*start_vel*T[1] - 6.0*end_vel*T[1]) / (2.0*T[5])

        return coefficients

    def sample_quintic_spline(self, coefficients, time):
        t = self.generate_powers(5, time)   # create powers of time

        position = (t[0] * coefficients[0] +
                    t[1] * coefficients[1] +
                    t[2] * coefficients[2] +
                    t[3] * coefficients[3] +
                    t[4] * coefficients[4] +
                    t[5] * coefficients[5])

        velocity = (1.0 * t[0] * coefficients[1] +
                    2.0 * t[1] * coefficients[2] +
                    3.0 * t[2] * coefficients[3] +
                    4.0 * t[3] * coefficients[4] +
                    5.0 * t[4] * coefficients[5])

        acceleration = ( 2.0 * t[0] * coefficients[2] +
                         6.0 * t[1] * coefficients[3] +
                        12.0 * t[2] * coefficients[4] +
                        20.0 * t[3] * coefficients[5])

        return position, velocity, acceleration

    def sample_spline_with_time_bounds(self, coefficients, duration, time):
        if time < 0:
            position, velocity, acceleration = self.sample_quintic_spline(coefficients, 0.0)
            velocity = 0.0
            acceleration = 0.0
        elif time > duration:
            position, velocity, acceleration = self.sample_quintic_spline(coefficients, duration)
            velocity = 0.0
            acceleration = 0.0
        else:
            position, velocity, acceleration = self.sample_quintic_spline(coefficients, time)

        return position, velocity, acceleration



    ##################################################################
    #------------------------ Angles functions ----------------------#
    ##################################################################

    def normalize_angle_positive(self, angle):
        return fmod(fmod(angle, 2.0 * pi) + 2.0 * pi, 2.0 * pi)

    def normalize_angle(self, angle):
        a = self.normalize_angle_positive(angle)
        if a > pi: a -= 2.0 * pi
        return a

    def shortest_angular_distance(self, fr, to):
        result = self.normalize_angle_positive(self.normalize_angle_positive(to) - self.normalize_angle_positive(fr))

        # If the result > 180, it's shorter the other way.
        if result > pi: result = -(2.0 * pi - result)
        return self.normalize_angle(result)
