"""
3D Character Game with MPU6050 Control
The game expects data in format: 'Accel => X:val Y:val Z:val | Gyro => X:val Y:val Z:val'
"""

import sys
import math
import time
import threading
import re
import serial
import serial.tools.list_ports
import numpy as np
from collections import deque

try:
    import pygame
    from pygame.locals import *
    from OpenGL.GL import *
    from OpenGL.GLU import *
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Install with: pip install pygame PyOpenGL PyOpenGL-accelerate pyserial numpy")
    sys.exit(1)

class MPU6050Controller:
    def __init__(self, baudrate=115200, timeout=0.1):
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial_conn = None
        self.connected = False
        self.running = False
        
        # Data storage
        self.accel_data = {'x': 0.0, 'y': 0.0, 'z': 0.0}
        self.gyro_data = {'x': 0.0, 'y': 0.0, 'z': 0.0}
        
        # Smoothing and filtering
        self.smooth_factor = 0.15  # Reduced for smoother movement
        self.accel_history = deque(maxlen=10)  # Increased history for better smoothing
        self.deadzone = 0.05  # Small deadzone for stability
        self._lock = threading.Lock()
        
        # Calibration
        self.calibration_samples = []
        self.calibrated = False
        self.offset = {'x': 0.0, 'y': 0.0, 'z': 0.0}

    def scan_ports(self):
        """Print and return available serial ports"""
        print("\n" + "="*60)
        print("Available Serial Ports:")
        print("="*60)
        
        ports = list(serial.tools.list_ports.comports())
        for i, port in enumerate(ports):
            print(f"  [{i}] {port.device} - {port.description}")
        print()
        return ports

    def connect(self, port_hint=None):
        """Connect to MPU6050 device"""
        ports = self.scan_ports()
        
        if port_hint:
            try:
                print(f"Connecting to {port_hint}...")
                self.serial_conn = serial.Serial(port_hint, 
                                              baudrate=self.baudrate,
                                              timeout=self.timeout)
                self.connected = True
                print(f"✅ Connected to {port_hint}")
                return True
            except Exception as e:
                print(f"✗ Failed: {e}")
                
        # Try each port
        for port in ports:
            try:
                print(f"Trying {port.device}...")
                self.serial_conn = serial.Serial(port.device,
                                              baudrate=self.baudrate, 
                                              timeout=self.timeout)
                # Verify it's MPU6050 data
                for _ in range(5):
                    line = self.serial_conn.readline().decode('utf-8').strip()
                    if "|" in line and "Gyro =>" in line:
                        self.connected = True
                        print(f"✅ Found MPU6050 on {port.device}")
                        return True
                self.serial_conn.close()
            except:
                continue
                
        print("⚠️  No MPU6050 found - using keyboard controls")
        self.connected = False
        return False

    def start(self):
        """Start reading data"""
        if not self.connected:
            return False
        self.running = True
        self.data_thread = threading.Thread(target=self._data_loop, daemon=True)
        self.data_thread.start()
        return True

    def stop(self):
        """Stop reading and close connection"""
        self.running = False
        if self.data_thread and self.data_thread.is_alive():
            self.data_thread.join(timeout=0.5)
        if self.serial_conn:
            self.serial_conn.close()
        self.connected = False

    def _data_loop(self):
        """Main data reading loop"""
        while self.running and self.serial_conn:
            try:
                line = self.serial_conn.readline().decode('utf-8').strip()
                if not line:
                    continue
                
                # Parse MPU6050 data format
                if "Accel =>" in line and "Gyro =>" in line:
                    self._parse_mpu_data(line)
                    
            except Exception as e:
                print(f"Data read error: {e}")
                time.sleep(0.1)

    def _parse_mpu_data(self, line):
        """Parse data line from MPU6050 in format: Y:-0.02 Z:-0.39 | Gyro => X:-35.55 Y:7.18 Z:-3.84"""
        try:
            # Split accel and gyro data
            parts = line.split("|")
            if len(parts) != 2:
                return
                
            accel_part = parts[0].strip()
            gyro_part = parts[1].strip()
            
            # Parse accelerometer data (Y and Z values)
            accel_matches = re.findall(r"([YZ]):(-?\d+\.\d+)", accel_part)
            for axis, value in accel_matches:
                self.accel_data[axis.lower()] = float(value)
            
            # Parse gyroscope data
            gyro_matches = re.findall(r"([XYZ]):(-?\d+\.\d+)", gyro_part)
            for axis, value in gyro_matches:
                self.gyro_data[axis.lower()] = float(value)
            
            # Calculate X from Y and Z using simple trigonometry
            # We'll use Y for forward/backward and Z for left/right tilt
            self.accel_data['x'] = -self.accel_data['z']  # Use negative Z for X movement
            
            # Store history for smoothing
            self.accel_history.append((
                self.accel_data['z'],  # Use Z for X movement (left/right)
                self.accel_data['y'],  # Use Y for Y movement (forward/backward)
                0.0
            ))
            
        except Exception as e:
            print(f"Parse error: {e}")

    def get_motion(self):
        """Get smoothed motion values for character control"""
        if not self.connected:
            return {'x': 0.0, 'y': 0.0, 'rotation': 0.0}
            
        with self._lock:
            if not self.accel_history:
                return {'x': 0.0, 'y': 0.0, 'rotation': 0.0}
            
            # Calculate weighted average of recent readings
            weights = np.linspace(0.5, 1.0, len(self.accel_history))
            weights /= weights.sum()
            
            x_values = [d[0] for d in self.accel_history]
            y_values = [d[1] for d in self.accel_history]
            
            avg_x = np.average(x_values, weights=weights)
            avg_y = np.average(y_values, weights=weights)
            
            # Apply deadzone
            deadzone = 0.1
            if abs(avg_x) < deadzone:
                avg_x = 0
            if abs(avg_y) < deadzone:
                avg_y = 0
            
            # Apply smooth acceleration curve
            x_norm = np.clip(avg_x, -1, 1)
            y_norm = np.clip(avg_y, -1, 1)
            
            # Square the values while preserving sign for more precise control
            x_norm = math.copysign(x_norm * x_norm, x_norm)
            y_norm = math.copysign(y_norm * y_norm, y_norm)
            
            return {
                'x': x_norm * 2.0,  # Increased sensitivity
                'y': y_norm * 2.0,  # Increased sensitivity
                'rotation': self.gyro_data['z'] * 0.3  # Reduced rotation sensitivity
            }

class Character3D:
    def __init__(self):
        # Character position and movement
        self.position = np.array([0.0, 0.0, 0.0])
        self.rotation = 0.0  # Y-axis rotation (facing direction)
        self.velocity = np.array([0.0, 0.0, 0.0])
        
        # Physics parameters
        self.speed = 0.2
        self.turn_speed = 2.0
        self.jump_force = 0.5
        self.gravity = 0.02
        self.ground_level = 0.0
        self.is_jumping = False
        
        # Animation
        self.walking = False
        self.walk_cycle = 0.0
        
        # Character colors
        self.colors = {
            'body': (0.2, 0.6, 0.8),
            'head': (0.8, 0.7, 0.6),
            'limbs': (0.2, 0.5, 0.7)
        }

    def update(self, motion):
        # Update rotation based on gyro with smooth interpolation
        target_rotation = self.rotation + motion['rotation'] * self.turn_speed
        self.rotation = self.rotation * 0.9 + target_rotation * 0.1
        
        # Calculate movement direction
        move_angle = math.radians(self.rotation)
        forward = np.array([math.sin(move_angle), 0, math.cos(move_angle)])
        right = np.array([math.cos(move_angle), 0, -math.sin(move_angle)])
        
        # Calculate target velocity
        target_velocity = (forward * -motion['y'] + right * motion['x']) * self.speed
        
        # Smoothly interpolate current velocity towards target
        self.velocity = self.velocity * 0.8 + target_velocity * 0.2
        
        # Apply additional friction when not moving
        if np.linalg.norm(target_velocity) < 0.01:
            self.velocity *= 0.9
        
        # Update position
        self.position += self.velocity
        
        # Apply gravity and jumping physics
        if self.position[1] > self.ground_level or self.is_jumping:
            self.velocity[1] -= self.gravity
            self.position[1] += self.velocity[1]
        
        # Ground collision with bounce effect
        if self.position[1] < self.ground_level:
            self.position[1] = self.ground_level
            if self.velocity[1] < -0.1:  # Only bounce on hard landings
                self.velocity[1] = -self.velocity[1] * 0.2  # 20% bounce
            else:
                self.velocity[1] = 0
            self.is_jumping = False
        
        # Update walking animation with speed-based cycle
        speed = np.linalg.norm(self.velocity[:2])
        if speed > 0.01:
            self.walking = True
            self.walk_cycle += speed * 2.0  # Animation speed based on movement speed
        else:
            self.walking = False
            self.walk_cycle = 0
        
        # Boundary limits with smooth bounce
        for i in [0, 2]:  # X and Z coordinates
            if abs(self.position[i]) > 20:
                self.position[i] = 20 if self.position[i] > 0 else -20
                self.velocity[i] *= -0.5  # Bounce with energy loss

    def jump(self):
        if not self.is_jumping and self.position[1] <= self.ground_level:
            self.velocity[1] = self.jump_force
            self.is_jumping = True

    def draw(self):
        """Draw the 3D character with animations"""
        glPushMatrix()
        glTranslatef(*self.position)
        glRotatef(self.rotation, 0, 1, 0)
        
        # Draw body
        glColor3f(*self.colors['body'])
        self._draw_box(0, 1.0, 0, 0.4, 0.6, 0.2)
        
        # Draw head
        glColor3f(*self.colors['head'])
        self._draw_box(0, 1.8, 0, 0.3, 0.3, 0.3)
        
        # Draw arms with swing animation
        glColor3f(*self.colors['limbs'])
        if self.walking:
            arm_swing = math.sin(self.walk_cycle) * 30
            # Left arm
            glPushMatrix()
            glTranslatef(-0.3, 1.4, 0)
            glRotatef(arm_swing, 1, 0, 0)
            self._draw_box(0, -0.3, 0, 0.1, 0.4, 0.1)
            glPopMatrix()
            
            # Right arm
            glPushMatrix()
            glTranslatef(0.3, 1.4, 0)
            glRotatef(-arm_swing, 1, 0, 0)
            self._draw_box(0, -0.3, 0, 0.1, 0.4, 0.1)
            glPopMatrix()
        else:
            self._draw_box(-0.3, 1.1, 0, 0.1, 0.4, 0.1)
            self._draw_box(0.3, 1.1, 0, 0.1, 0.4, 0.1)
        
        # Draw legs with walk animation
        if self.walking:
            leg_swing = math.sin(self.walk_cycle) * 40
            # Left leg
            glPushMatrix()
            glTranslatef(-0.15, 0.7, 0)
            glRotatef(leg_swing, 1, 0, 0)
            self._draw_box(0, -0.3, 0, 0.1, 0.4, 0.1)
            glPopMatrix()
            
            # Right leg
            glPushMatrix()
            glTranslatef(0.15, 0.7, 0)
            glRotatef(-leg_swing, 1, 0, 0)
            self._draw_box(0, -0.3, 0, 0.1, 0.4, 0.1)
            glPopMatrix()
        else:
            self._draw_box(-0.15, 0.4, 0, 0.1, 0.4, 0.1)
            self._draw_box(0.15, 0.4, 0, 0.1, 0.4, 0.1)
        
        glPopMatrix()
        
        # Draw shadow
        self._draw_shadow()

    def _draw_box(self, x, y, z, width, height, depth):
        """Draw a 3D box"""
        glPushMatrix()
        glTranslatef(x, y, z)
        glScalef(width, height, depth)
        
        glBegin(GL_QUADS)
        # Front
        glNormal3f(0, 0, 1)
        glVertex3f(-1, -1, 1)
        glVertex3f(1, -1, 1)
        glVertex3f(1, 1, 1)
        glVertex3f(-1, 1, 1)
        
        # Back
        glNormal3f(0, 0, -1)
        glVertex3f(-1, -1, -1)
        glVertex3f(-1, 1, -1)
        glVertex3f(1, 1, -1)
        glVertex3f(1, -1, -1)
        
        # Top
        glNormal3f(0, 1, 0)
        glVertex3f(-1, 1, -1)
        glVertex3f(-1, 1, 1)
        glVertex3f(1, 1, 1)
        glVertex3f(1, 1, -1)
        
        # Bottom
        glNormal3f(0, -1, 0)
        glVertex3f(-1, -1, -1)
        glVertex3f(1, -1, -1)
        glVertex3f(1, -1, 1)
        glVertex3f(-1, -1, 1)
        
        # Right
        glNormal3f(1, 0, 0)
        glVertex3f(1, -1, -1)
        glVertex3f(1, 1, -1)
        glVertex3f(1, 1, 1)
        glVertex3f(1, -1, 1)
        
        # Left
        glNormal3f(-1, 0, 0)
        glVertex3f(-1, -1, -1)
        glVertex3f(-1, -1, 1)
        glVertex3f(-1, 1, 1)
        glVertex3f(-1, 1, -1)
        
        glEnd()
        glPopMatrix()

    def _draw_shadow(self):
        """Draw character shadow"""
        glPushMatrix()
        glTranslatef(self.position[0], 0.01, self.position[2])
        glRotatef(self.rotation, 0, 1, 0)
        
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDisable(GL_LIGHTING)
        
        glColor4f(0.0, 0.0, 0.0, 0.3)
        glBegin(GL_QUADS)
        glVertex3f(-0.2, 0, -0.3)
        glVertex3f(0.2, 0, -0.3)
        glVertex3f(0.2, 0, 0.3)
        glVertex3f(-0.2, 0, 0.3)
        glEnd()
        
        glEnable(GL_LIGHTING)
        glDisable(GL_BLEND)
        glPopMatrix()

class Game:
    def __init__(self):
        pygame.init()
        self.display = (1200, 800)
        pygame.display.set_mode(self.display, DOUBLEBUF | OPENGL)
        pygame.display.set_caption("3D Character Game - MPU6050 Control")
        
        # OpenGL setup
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)
        glEnable(GL_LIGHT0)
        glEnable(GL_COLOR_MATERIAL)
        glShadeModel(GL_SMOOTH)
        
        glMatrixMode(GL_PROJECTION)
        gluPerspective(45, (self.display[0]/self.display[1]), 0.1, 50.0)
        
        # Lighting setup
        glLightfv(GL_LIGHT0, GL_POSITION, (5, 5, 5, 1))
        glLightfv(GL_LIGHT0, GL_AMBIENT, (0.3, 0.3, 0.3, 1))
        glLightfv(GL_LIGHT0, GL_DIFFUSE, (0.8, 0.8, 0.8, 1))
        
        self.character = Character3D()
        self.mpu_controller = MPU6050Controller()
        
        # Try to connect to MPU6050
        if not self.mpu_controller.connect():
            print("⚠️  Using keyboard controls")
        else:
            self.mpu_controller.start()
        
        self.camera_angle = 0
        self.camera_height = 10
        self.camera_distance = 15
        
        self.running = True
        self.clock = pygame.time.Clock()
        self.fps = 60

    def handle_input(self):
        """Process keyboard and MPU6050 input"""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                elif event.key == pygame.K_SPACE:
                    self.character.jump()
        
        # Get motion data (from MPU6050 or keyboard)
        if self.mpu_controller.connected:
            motion = self.mpu_controller.get_motion()
        else:
            # Keyboard fallback
            keys = pygame.key.get_pressed()
            motion = {
                'x': (keys[pygame.K_d] - keys[pygame.K_a]) * 0.5,
                'y': (keys[pygame.K_w] - keys[pygame.K_s]) * 0.5,
                'rotation': (keys[pygame.K_LEFT] - keys[pygame.K_RIGHT]) * 2.0
            }
        
        return motion

    def update_camera(self):
        """Update camera position to follow character"""
        # Calculate camera position
        target = self.character.position
        angle_rad = math.radians(self.character.rotation + self.camera_angle)
        
        cam_x = target[0] - math.sin(angle_rad) * self.camera_distance
        cam_z = target[2] - math.cos(angle_rad) * self.camera_distance
        cam_y = target[1] + self.camera_height
        
        # Set camera view
        glLoadIdentity()
        gluLookAt(cam_x, cam_y, cam_z,  # Camera position
                  target[0], target[1] + 1, target[2],  # Look at point
                  0, 1, 0)  # Up vector

    def draw_world(self):
        """Draw the 3D world"""
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        self.update_camera()
        
        # Draw ground grid
        glBegin(GL_LINES)
        glColor3f(0.3, 0.3, 0.3)
        for i in range(-20, 21, 2):
            glVertex3f(i, 0, -20)
            glVertex3f(i, 0, 20)
            glVertex3f(-20, 0, i)
            glVertex3f(20, 0, i)
        glEnd()
        
        # Draw character
        self.character.draw()
        
        # Draw HUD
        self.draw_hud()
        
        pygame.display.flip()

    def draw_hud(self):
        """Draw HUD with game info"""
        font = pygame.font.Font(None, 36)
        
        if self.mpu_controller.connected:
            status = "Connected to MPU6050"
            color = (0, 255, 0)
        else:
            status = "Keyboard Controls (WASD + Arrows)"
            color = (255, 255, 0)
        
        text = font.render(status, True, color)
        text_data = pygame.image.tostring(text, "RGBA", True)
        
        # Save matrices
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        glOrtho(0, self.display[0], self.display[1], 0, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()
        
        # Disable lighting for HUD
        glDisable(GL_LIGHTING)
        glDisable(GL_DEPTH_TEST)
        
        # Draw text
        glRasterPos2i(10, 30)
        glDrawPixels(text.get_width(), text.get_height(), 
                    GL_RGBA, GL_UNSIGNED_BYTE, text_data)
        
        # Restore state
        glEnable(GL_LIGHTING)
        glEnable(GL_DEPTH_TEST)
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)
        glPopMatrix()

    def run(self):
        """Main game loop"""
        while self.running:
            motion = self.handle_input()
            self.character.update(motion)
            self.draw_world()
            self.clock.tick(self.fps)
        
        # Cleanup
        if self.mpu_controller:
            self.mpu_controller.stop()
        pygame.quit()

if __name__ == "__main__":
    try:
        game = Game()
        game.run()
    except Exception as e:
        print(f"Error: {e}")
        pygame.quit()