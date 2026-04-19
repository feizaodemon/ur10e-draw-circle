from robodk import robolink, robomath, robodialogs
import os
import urllib.request

robolink.import_install("svgpathtools")
import svgpathtools as spt

# -------------------------------------------
# Scene item names
FRAME_NAME = "Draw Frame"
HOME_TARGET_NAME = "Target 1"
BOARD_OBJECT_NAME = "Whiteboard 250mm"
DRAWING_BOARD_NAME = "Drawing Board"
CANVAS_NAME = "Art Canvas"
PIXEL_REF_NAME = "pixel"

# Robot configuration
REAL_ROBOT = True
DRY_RUN = True
TOOL_PAYLOAD_KG = 0.5

# SVG and drawing settings
IMAGE_FILE = ""
MAX_DRAW_WIDTH, MAX_DRAW_HEIGHT = 600.0, 450.0
BOARD_BACKGROUND_COLOR = [0, 0, 0, 1]

DEFAULT_PATH_COLOR = "#FFFFFF"
USE_STYLE_COLOR = True
PREFER_STROKE_OVER_FILL_COLOR = True

TCP_KEEP_TANGENCY = False
APPROACH = 100.0

# Motion settings
PEN_Z_OFFSET = 0.0
SPEED_HOVER = 200.0
SPEED_PLUNGE = 10.0
SPEED_DRAW = 50.0
MM_X_PIXEL = 5.0
ROUNDING_MM = 2.0
PIXEL_SIZE = 3.0

# Safer first-pass parameters for real hardware validation
DRY_RUN_MAX_DRAW_WIDTH, DRY_RUN_MAX_DRAW_HEIGHT = 200.0, 150.0
DRY_RUN_PEN_Z_OFFSET = 5.0
DRY_RUN_SPEED_HOVER = 100.0
DRY_RUN_SPEED_PLUNGE = 5.0
DRY_RUN_SPEED_DRAW = 20.0
DRY_RUN_MM_X_PIXEL = 8.0

if REAL_ROBOT and DRY_RUN:
    MAX_DRAW_WIDTH, MAX_DRAW_HEIGHT = DRY_RUN_MAX_DRAW_WIDTH, DRY_RUN_MAX_DRAW_HEIGHT
    PEN_Z_OFFSET = DRY_RUN_PEN_Z_OFFSET
    SPEED_HOVER = DRY_RUN_SPEED_HOVER
    SPEED_PLUNGE = DRY_RUN_SPEED_PLUNGE
    SPEED_DRAW = DRY_RUN_SPEED_DRAW
    MM_X_PIXEL = DRY_RUN_MM_X_PIXEL


def extract_styles(attrib):
    styles = {}
    if "style" not in attrib:
        if "fill" in attrib:
            styles["fill"] = attrib["fill"]
        if "stroke" in attrib:
            styles["stroke"] = attrib["stroke"]
    else:
        for style in attrib["style"].split(";"):
            style_pair = style.split(":")
            if len(style_pair) != 2:
                continue
            styles[style_pair[0].strip()] = style_pair[1].strip()

    if "fill" in styles and not styles["fill"].startswith("#"):
        styles.pop("fill")
    if "stroke" in styles and not styles["stroke"].startswith("#"):
        styles.pop("stroke")
    return styles


def choose_hex_color(styles):
    hex_color = DEFAULT_PATH_COLOR
    if USE_STYLE_COLOR:
        if PREFER_STROKE_OVER_FILL_COLOR:
            if "stroke" in styles:
                hex_color = styles["stroke"]
            elif "fill" in styles:
                hex_color = styles["fill"]
        else:
            if "fill" in styles:
                hex_color = styles["fill"]
            elif "stroke" in styles:
                hex_color = styles["stroke"]
    return hex_color


# -------------------------------------------
# Load the SVG file
if IMAGE_FILE.startswith("http") and IMAGE_FILE.endswith(".svg"):
    urllib.request.urlretrieve(IMAGE_FILE, "drawing.svg")
    IMAGE_FILE = "drawing.svg"
elif not IMAGE_FILE or not os.path.exists(os.path.abspath(IMAGE_FILE)):
    IMAGE_FILE = robodialogs.getOpenFileName(
        strtitle="Open SVG File",
        defaultextension=".svg",
        filetypes=[("SVG files", ".svg")],
    )

if not IMAGE_FILE or not os.path.exists(os.path.abspath(IMAGE_FILE)):
    quit()

print("Loading SVG file:", IMAGE_FILE)
paths, path_attribs, svg_attribs = spt.svg2paths2(IMAGE_FILE)
print("SVG file loaded, paths count:", len(paths))

# Compute SVG bounds
xmin, xmax, ymin, ymax = 9e9, 0, 9e9, 0
for path in paths:
    _xmin, _xmax, _ymin, _ymax = path.bbox()
    xmin = min(_xmin, xmin)
    xmax = max(_xmax, xmax)
    ymin = min(_ymin, ymin)
    ymax = max(_ymax, ymax)

bbox_height, bbox_width = ymax - ymin, xmax - xmin
SCALE = min(MAX_DRAW_HEIGHT / bbox_height, MAX_DRAW_WIDTH / bbox_width)
svg_height, svg_width = bbox_height * SCALE, bbox_width * SCALE
svg_height_min, svg_width_min = ymin * SCALE, xmin * SCALE

# -------------------------------------------
# Get RoboDK items
print("Connecting to RoboDK...")
RDK = robolink.Robolink()
print("Connected to RoboDK.")
RDK.setSelection([])

robot = RDK.Item("", robolink.ITEM_TYPE_ROBOT)
tool = robot.getLink(robolink.ITEM_TYPE_TOOL)
if not robot.Valid() or not tool.Valid():
    print("Error: robot or tool not found.")
    quit()

robot.setParamRobotTool(TOOL_PAYLOAD_KG)
robot.RunInstruction(f"set_payload({TOOL_PAYLOAD_KG})", robolink.INSTRUCTION_INSERT_CODE)
print(f"Payload set to {TOOL_PAYLOAD_KG} kg")

frame = RDK.Item(FRAME_NAME, robolink.ITEM_TYPE_FRAME)
if not frame.Valid():
    print(f"Error: frame '{FRAME_NAME}' not found.")
    quit()

pixel_ref = RDK.Item(PIXEL_REF_NAME)
if not pixel_ref.Valid():
    RDK.ShowMessage(f"Reference object '{PIXEL_REF_NAME}' not found.", False)

RDK.Render(False)

board_draw = RDK.Item(DRAWING_BOARD_NAME)
if board_draw.Valid() and board_draw.Type() == robolink.ITEM_TYPE_OBJECT:
    board_draw.Delete()

board_250mm = RDK.Item(BOARD_OBJECT_NAME)
if board_250mm.Valid():
    board_250mm.setVisible(False)
    board_250mm.Copy()
    board_draw = frame.Paste()
    board_draw.setVisible(True, False)
    board_draw.setName(DRAWING_BOARD_NAME)
    board_draw.Scale([2000 / 250, 1000 / 250, 1])
    board_draw.setColor(BOARD_BACKGROUND_COLOR)

canvas = RDK.Item(CANVAS_NAME)
if canvas.Valid():
    canvas.Delete()
if pixel_ref.Valid():
    pixel_ref.Copy()
    canvas = frame.Paste()
    canvas.setName(CANVAS_NAME)
    canvas.setVisible(True, False)
    canvas.setColor([0, 0, 0, 0])

my_pixel = None
if pixel_ref.Valid():
    pixel_ref.Copy()
    my_pixel = frame.Paste()
    my_pixel.setVisible(False)
    my_pixel.Scale([PIXEL_SIZE, PIXEL_SIZE, PIXEL_SIZE])

RDK.setSelection([])
RDK.Render(True)

# -------------------------------------------
# Initialize the robot
home_target = RDK.Item(HOME_TARGET_NAME, robolink.ITEM_TYPE_TARGET)
if not home_target.Valid():
    RDK.ShowMessage(f"Please create a target named '{HOME_TARGET_NAME}'.")
    quit()

home_joints = home_target.Joints().tolist()

print("Moving robot to home joints...")
if REAL_ROBOT and DRY_RUN:
    print("Dry-run mode enabled: testing above the board with reduced size and speed.")
robot.setPoseFrame(frame)
robot.setPoseTool(tool)
robot.MoveJ(home_joints)
print("Robot moved to home joints.")

orient_frame2tool = robomath.invH(frame.Pose()) * robot.SolveFK(home_joints) * tool.Pose()
CENTER_X = orient_frame2tool.Pos()[0]
CENTER_Y = orient_frame2tool.Pos()[1]

TRANSLATE_REAL = CENTER_Y - (svg_width / 2 + svg_width_min)
TRANSLATE_IMAG = CENTER_X - (svg_height / 2 + svg_height_min)
TRANSLATE = complex(TRANSLATE_REAL, TRANSLATE_IMAG)

orient_frame2tool[0:3, 3] = robomath.Mat([0, 0, 0])

RDK.ShowMessage("Drawing SVG centered at home target.", False)

for path_count, (path, attrib) in enumerate(zip(paths, path_attribs)):
    styles = extract_styles(attrib)
    hex_color = choose_hex_color(styles)
    draw_color = spt.misctools.hex2rgb(hex_color)
    draw_color = [round(x / 255, 4) for x in draw_color]

    approach_done = False
    prev_point = None

    for segment in path.scaled(SCALE).translated(TRANSLATE):
        segment_len = segment.length()
        steps = int(segment_len / MM_X_PIXEL)
        print(f"Drawing segment with {steps} steps...")
        if steps < 1:
            continue

        for i in range(steps + 1):
            if i % 10 == 0:
                print(f"  Step {i}/{steps}")

            t = 1.0
            if i < steps:
                i_len = segment_len * i / steps
                t = segment.ilength(i_len)

            point = segment.point(t)
            py, px = point.real, point.imag

            pa = 0.0
            if prev_point:
                v = point - prev_point
                norm_v = robomath.sqrt(v.real * v.real + v.imag * v.imag)
                v = v / norm_v if norm_v > 1e-6 else complex(1, 0)
                pa = robomath.atan2(v.real, v.imag)

            if not approach_done and i == 0:
                target0 = robomath.transl(px, py, PEN_Z_OFFSET) * orient_frame2tool * robomath.rotz(pa)
                target0_app = target0 * robomath.transl(0, 0, -APPROACH)

                ik_sol = robot.SolveIK(target0_app, home_joints)
                if len(ik_sol.tolist()) == 0:
                    RDK.ShowMessage("IK failed for the approach point.", False)
                    print("IK Failed for approach point. target0_app:", target0_app)
                    quit()

                robot.setSpeed(SPEED_HOVER)
                robot.MoveJ(target0_app)

                robot.setSpeed(SPEED_PLUNGE)
                robot.MoveJ(target0)

                approach_done = True
                continue

            point_pose = robomath.transl(px, py, PEN_Z_OFFSET) * robomath.rotz(pa)
            if TCP_KEEP_TANGENCY:
                robot_pose = point_pose * orient_frame2tool
            else:
                robot_pose = robomath.transl(px, py, PEN_Z_OFFSET) * orient_frame2tool

            try:
                robot.setSpeed(SPEED_DRAW)
                robot.setRounding(ROUNDING_MM)
                robot.MoveL(robot_pose)
            except Exception:
                msg = (
                    "Robot could not reach a point on the drawing path. "
                    f"Offset from center: x={px - CENTER_X:.1f} mm, y={py - CENTER_Y:.1f} mm"
                )
                RDK.ShowMessage(msg, False)
                print(msg)
                quit()

            if my_pixel and my_pixel.Valid() and canvas.Valid():
                my_pixel.Recolor(draw_color)
                canvas.AddGeometry(my_pixel, point_pose)

            prev_point = point

    if approach_done:
        target_app = robot_pose * robomath.transl(0, 0, -APPROACH)
        robot.setSpeed(SPEED_HOVER)
        robot.MoveJ(target_app)

robot.setSpeed(SPEED_HOVER)
robot.MoveJ(home_joints)

if my_pixel and my_pixel.Valid():
    my_pixel.Delete()

RDK.ShowMessage("Done drawing SVG!", False)
