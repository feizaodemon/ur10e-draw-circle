from robodk import robolink, robomath
import math

# Motion settings
PEN_Z_OFFSET = 0.0
SPEED_HOVER = 200.0
SPEED_PLUNGE = 10.0
SPEED_DRAW = 50.0
APPROACH = 100.0

# Circle settings
RADIUS = 150.0
ARC_SEGMENTS = 4
VISUAL_POINTS_COUNT = 360
PIXEL_SIZE = 2.0
TOOL_PAYLOAD_KG = 0.5


def circle_xy(center_x, center_y, radius, angle_rad):
    x = center_x + radius * math.cos(angle_rad)
    y = center_y + radius * math.sin(angle_rad)
    return x, y


def circle_pose(center_x, center_y, radius, angle_rad, z_offset, tool_orientation):
    x, y = circle_xy(center_x, center_y, radius, angle_rad)
    return robomath.transl(x, y, z_offset) * tool_orientation


RDK = robolink.Robolink()
robot = RDK.Item("", robolink.ITEM_TYPE_ROBOT)
tool = robot.getLink(robolink.ITEM_TYPE_TOOL)
frame = RDK.Item("Draw Frame", robolink.ITEM_TYPE_FRAME)
home_target = RDK.Item("Target 1", robolink.ITEM_TYPE_TARGET)

if not robot.Valid() or not frame.Valid() or not home_target.Valid():
    print("Environment error: robot, Draw Frame, or Target 1 was not found.")
    quit()

robot.setParamRobotTool(TOOL_PAYLOAD_KG)
robot.RunInstruction(
    f"set_payload({TOOL_PAYLOAD_KG})", robolink.INSTRUCTION_INSERT_CODE
)
print(f"Payload set to {TOOL_PAYLOAD_KG} kg")

board_draw = RDK.Item("Drawing Board")
if board_draw.Valid() and board_draw.Type() == robolink.ITEM_TYPE_OBJECT:
    board_draw.Delete()

board_250mm = RDK.Item("Whiteboard 250mm")
if board_250mm.Valid():
    board_250mm.setVisible(False)
    board_250mm.Copy()
    board_draw = frame.Paste()
    board_draw.setVisible(True, False)
    board_draw.setName("Drawing Board")
    board_draw.Scale([2000 / 250, 1000 / 250, 1])
    board_draw.setColor([0, 0, 0, 1])

pixel_ref = RDK.Item("pixel")

canvas = RDK.Item("Art Canvas")
if canvas.Valid():
    canvas.Delete()
if pixel_ref.Valid():
    pixel_ref.Copy()
    canvas = frame.Paste()
    canvas.setName("Art Canvas")
    canvas.setVisible(True, False)
    canvas.setColor([0, 0, 0, 0])

my_pixel = None
if pixel_ref.Valid():
    pixel_ref.Copy()
    my_pixel = frame.Paste()
    my_pixel.setVisible(False)
    my_pixel.Scale([PIXEL_SIZE, PIXEL_SIZE, PIXEL_SIZE])
    my_pixel.Recolor([1, 1, 1, 1])

home_joints = home_target.Joints().tolist()

print("Moving to home...")
robot.setPoseFrame(frame)
robot.setPoseTool(tool)
robot.setSpeed(SPEED_HOVER)
robot.MoveJ(home_joints)

orient_frame2tool = robomath.invH(frame.Pose()) * robot.SolveFK(home_joints) * tool.Pose()
CENTER_X = orient_frame2tool.Pos()[0]
CENTER_Y = orient_frame2tool.Pos()[1]
orient_frame2tool[0:3, 3] = robomath.Mat([0, 0, 0])

print(f"Drawing a circle with radius {RADIUS} mm...")

arc_targets = []
for segment_idx in range(ARC_SEGMENTS):
    start_angle = 2 * math.pi * segment_idx / ARC_SEGMENTS
    mid_angle = start_angle + math.pi / ARC_SEGMENTS
    end_angle = start_angle + 2 * math.pi / ARC_SEGMENTS
    arc_targets.append((start_angle, mid_angle, end_angle))

approach_done = False
robot_pose = None

for start_angle, mid_angle, end_angle in arc_targets:
    start_pose = circle_pose(
        CENTER_X, CENTER_Y, RADIUS, start_angle, PEN_Z_OFFSET, orient_frame2tool
    )
    mid_pose = circle_pose(
        CENTER_X, CENTER_Y, RADIUS, mid_angle, PEN_Z_OFFSET, orient_frame2tool
    )
    end_pose = circle_pose(
        CENTER_X, CENTER_Y, RADIUS, end_angle, PEN_Z_OFFSET, orient_frame2tool
    )

    if not approach_done:
        target_app = start_pose * robomath.transl(0, 0, -APPROACH)
        robot.setSpeed(SPEED_HOVER)
        robot.MoveJ(target_app)

        robot.setSpeed(SPEED_PLUNGE)
        robot.MoveJ(start_pose)
        approach_done = True

    robot.setSpeed(SPEED_DRAW)
    robot.setRounding(0.0)
    robot.MoveC(mid_pose, end_pose)
    robot_pose = end_pose

if my_pixel and my_pixel.Valid() and canvas.Valid():
    for i in range(VISUAL_POINTS_COUNT):
        angle = 2 * math.pi * i / VISUAL_POINTS_COUNT
        px, py = circle_xy(CENTER_X, CENTER_Y, RADIUS, angle)
        tangent_angle = angle + math.pi / 2
        point_pose = robomath.transl(px, py, PEN_Z_OFFSET) * robomath.rotz(tangent_angle)
        canvas.AddGeometry(my_pixel, point_pose)

if approach_done and robot_pose is not None:
    target_app = robot_pose * robomath.transl(0, 0, -APPROACH)
    robot.setSpeed(SPEED_HOVER)
    robot.MoveJ(target_app)

robot.MoveJ(home_joints)

if my_pixel and my_pixel.Valid():
    my_pixel.Delete()

print("Circle drawing complete.")
