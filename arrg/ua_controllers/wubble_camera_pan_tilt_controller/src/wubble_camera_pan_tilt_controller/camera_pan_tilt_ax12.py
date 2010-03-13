#!/usr/bin/env python
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

import roslib
roslib.load_manifest('wubble_camera_pan_tilt_controller')

from ax12_driver_core.joint_position_controller import JointPositionControllerAX12

class DriverControl:
    def __init__(self, out_cb, joint_controllers):
        self.camera_pan_tilt = CameraPanTiltAX12(out_cb, joint_controllers)
        
    def initialize(self):
        return self.camera_pan_tilt.initialize()
        
    def start(self):
        self.camera_pan_tilt.start()
        
    def stop(self):
        self.camera_pan_tilt.stop()

class CameraPanTiltAX12():
    def __init__(self, out_cb, joint_controllers):
        self.pan_controller = JointPositionControllerAX12(out_cb, joint_controllers[0])
        self.tilt_controller = JointPositionControllerAX12(out_cb, joint_controllers[1])

    def initialize(self):
        success = self.pan_controller.initialize() and self.tilt_controller.initialize()
        if success:
            self.pan_controller.set_speed(1.17)
            self.tilt_controller.set_speed(1.17)
        return success
        
    def start(self):
        self.pan_controller.start()
        self.tilt_controller.start()
        
    def stop(self):
        self.pan_controller.stop()
        self.tilt_controller.stop()

