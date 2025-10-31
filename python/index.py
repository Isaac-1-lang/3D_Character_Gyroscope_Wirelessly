import pygame
import math
import serial
# ---------------------------
# Serial Setup
# ---------------------------
COM_PORT = "COM22"  # Arduino Bluetooth Serial Port
BAUD_RATE = 9600
ser = serial.Serial(COM_PORT, BAUD_RATE, timeout=1)
# ---------------------------
# Pygame Setup
# ---------------------------
WIDTH, HEIGHT = 800, 600
pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("3D Colored Cube Controlled by MPU6050")
clock = pygame.time.Clrock()
# ---------------------------
# Cube Definition
# ---------------------------
cube_vertices = [
    [-1, -1, -1],  # 0
    [1, -1, -1],   # 1
    [1, 1, -1],    # 2
    [-1, 1, -1],   # 3
    [-1, -1, 1],   # 4
    [1, -1, 1],    # 5
    [1, 1, 1],     # 6
    [-1, 1, 1],    # 7
]
# Each face as 4 vertices (by index)
cube_faces = [
    (0, 1, 2, 3),  # back - red
    (4, 5, 6, 7),  # front - green
    (0, 1, 5, 4),  # bottom - blue
    (2, 3, 7, 6),  # top - yellow
    (1, 2, 6, 5),  # right - cyan
    (0, 3, 7, 4),  # left - magenta
]
face_colors = [
    (255, 0, 0),    # red
    (0, 255, 0),    # green
    (0, 0, 255),    # blue
    (255, 255, 0),  # yellow
    (0, 255, 255),  # cyan
    (255, 0, 255),  # magenta
]
SCALE = 100
OFFSET_X, OFFSET_Y = WIDTH//2, HEIGHT//2
# ---------------------------
# Functions
# ---------------------------
def rotate_point(x, y, z, ax, ay, az):
    # Rotation around X-axis
    cosx, sinx = math.cos(ax), math.sin(ax)
    y, z = y*cosx - z*sinx, y*sinx + z*cosx
    # Rotation around Y-axis
    cosy, siny = math.cos(ay), math.sin(ay)
    x, z = x*cosy + z*siny, -x*siny + z*cosy
    # Rotation around Z-axis
    cosz, sinz = math.cos(az), math.sin(az)
    x, y = x*cosz - y*sinz, x*sinz + y*cosz
    return x, y, z
def project(x, y, z):
    """Simple perspective projection"""
    factor = SCALE / (z + 5)
    x_proj = x * factor + OFFSET_X
    y_proj = -y * factor + OFFSET_Y
    return int(x_proj), int(y_proj)
# ---------------------------
# Main Loop
# ---------------------------
ax = ay = az = 0.0
running = True
while running:
    screen.fill((0, 0, 0))
    # Read Arduino data
    if ser.in_waiting:
        try:
            line = ser.readline().decode('utf-8').strip()
            if line:
                ax_raw, ay_raw, az_raw, gx, gy, gz = map(int, line.split(","))
                # Convert accelerometer values to rotation angles
                ax = math.radians(ax_raw / 16384 * 90)
                ay = math.radians(ay_raw / 16384 * 90)
                az = math.radians(az_raw / 16384 * 90)
        except:
            pass
    # Rotate all vertices
    transformed_vertices = []
    for v in cube_vertices:
        x, y, z = rotate_point(v[0], v[1], v[2], ax, ay, az)
        transformed_vertices.append((x, y, z))
    # Sort faces by average z (simple painter's algorithm)
    face_depths = []
    for i, face in enumerate(cube_faces):
        z_avg = sum(transformed_vertices[v][2] for v in face) / 4.0
        face_depths.append((i, z_avg))
    face_depths.sort(key=lambda x: x[1], reverse=True)  # farthest first
    # Draw faces
    for face_index, _ in face_depths:
        face = cube_faces[face_index]
        points = [project(*transformed_vertices[v]) for v in face]
        pygame.draw.polygon(screen, face_colors[face_index], points)
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
    pygame.display.flip()
    clock.tick(60)
pygame.quit()
ser.close()
