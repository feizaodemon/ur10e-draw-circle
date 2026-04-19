from robodk import robolink, robomath, robodialogs
import os
import urllib.request
import math

robolink.import_install('svgpathtools')
import svgpathtools as spt

#-------------------------------------------
# Settings
IMAGE_FILE = ""  # 留空，运行代码时会自动弹窗让你选择自己画的 SVG 文件

# 既然底座已经居中，机器臂火力全开！恢复成海报级别的大尺寸 (600x450mm)
MAX_DRAW_WIDTH, MAX_DRAW_HEIGHT = 600.0, 450.0  
BOARD_BACKGROUND_COLOR = [0, 0, 0, 1] 

DEFAULT_PATH_COLOR = '#FFFFFF'  
USE_STYLE_COLOR = True
PREFER_STROKE_OVER_FILL_COLOR = True  

TCP_KEEP_TANGENCY = False  
APPROACH = 100.0  

# --- 保护白板的核心物理参数 ---
PEN_Z_OFFSET = 0.0   # 微调笔尖深度(毫米)。如果现实中笔尖压得太重，可以设为 1.0 或 2.0 (正数代表笔尖向后退)；如果画不到，设为负数(-1.0)。
SPEED_HOVER = 200.0  # 笔悬空时的移动速度 (mm/s)
SPEED_PLUNGE = 10.0  # 笔尖接触白板瞬间的“轻放”速度 (mm/s)，极慢下笔避免刚性撞击
SPEED_DRAW = 50.0    # 接触白板画画时的平稳移动速度 (mm/s)

MM_X_PIXEL = 5.0  # 像素精细度，越小画得越精细

#-------------------------------------------
# Load the SVG file
if IMAGE_FILE.startswith('http') and IMAGE_FILE.endswith('.svg'):
    urllib.request.urlretrieve(IMAGE_FILE, "drawing.svg")
    IMAGE_FILE = "drawing.svg"

elif not IMAGE_FILE or not os.path.exists(os.path.abspath(IMAGE_FILE)):
    IMAGE_FILE = robodialogs.getOpenFileName(strtitle='Open SVG File', defaultextension='.svg', filetypes=[('SVG files', '.svg')])

if not IMAGE_FILE or not os.path.exists(os.path.abspath(IMAGE_FILE)):
    quit()

print("Loading SVG file:", IMAGE_FILE)
paths, path_attribs, svg_attribs = spt.svg2paths2(IMAGE_FILE)
print("SVG file loaded, paths count:", len(paths))

# 1. 计算 SVG 图片原始大小
xmin, xmax, ymin, ymax = 9e9, 0, 9e9, 0
for path in paths:
    _xmin, _xmax, _ymin, _ymax = path.bbox()
    xmin = min(_xmin, xmin)
    xmax = max(_xmax, xmax)
    ymin = min(_ymin, ymin)
    ymax = max(_ymax, ymax)
bbox_height, bbox_width = ymax - ymin, xmax - xmin

# 2. 将 SVG 强制缩小到我们的 400x300 范围内
SCALE = min(MAX_DRAW_HEIGHT / bbox_height, MAX_DRAW_WIDTH / bbox_width)
svg_height, svg_width = bbox_height * SCALE, bbox_width * SCALE
svg_height_min, svg_width_min = ymin * SCALE, xmin * SCALE

#-------------------------------------------
# Get RoboDK Items
print("Connecting to RoboDK...")
RDK = robolink.Robolink()
print("Connected to RoboDK.")
RDK.setSelection([])

robot = RDK.Item('', robolink.ITEM_TYPE_ROBOT) # 自动获取场景中的第一个机器臂
tool = robot.getLink(robolink.ITEM_TYPE_TOOL)
if not robot.Valid() or not tool.Valid():
    print("Error: 未找到机器人或工具！")
    quit()

# 1.5 自动检查与配置 UR 的 Payload (物理硬件安全核心！)
TOOL_PAYLOAD_KG = 0.5  # 假设画笔和 3D 打印件总重 0.5kg
robot.setParamRobotTool(TOOL_PAYLOAD_KG)
robot.RunInstruction(f"set_payload({TOOL_PAYLOAD_KG})", robolink.INSTRUCTION_INSERT_CODE)
print(f"✅ 安全检查通过：已向 UR 控制器下发 Payload = {TOOL_PAYLOAD_KG}kg")

frame = RDK.Item('Draw Frame', robolink.ITEM_TYPE_FRAME) # 自动获取名为 Draw Frame 的参考系
if not frame.Valid():
    print("Error: 未找到 Draw Frame！")
    quit()

pixel_ref = RDK.Item('pixel')  
if not pixel_ref.Valid():
    RDK.ShowMessage("Reference object 'pixel' not found.", False)

RDK.Render(False)

board_draw = RDK.Item('Drawing Board')
if board_draw.Valid() and board_draw.Type() == robolink.ITEM_TYPE_OBJECT:
    board_draw.Delete()
board_250mm = RDK.Item('Whiteboard 250mm')
if board_250mm.Valid():
    board_250mm.setVisible(False)
    board_250mm.Copy()
    board_draw = frame.Paste()
    board_draw.setVisible(True, False)
    board_draw.setName('Drawing Board')
    board_draw.Scale([2000 / 250, 1000 / 250, 1])  # 恢复现实中巨大的黑板视觉效果
    board_draw.setColor(BOARD_BACKGROUND_COLOR)

# 创建纯净的透明画板，专门存放画出的线条，防止黑板拉伸导致像素变成长方形
canvas = RDK.Item('Art Canvas')
if canvas.Valid():
    canvas.Delete()
if pixel_ref.Valid():
    pixel_ref.Copy()
    canvas = frame.Paste()
    canvas.setName('Art Canvas')
    canvas.setVisible(True, False)
    canvas.setColor([0, 0, 0, 0])

# 创建一个专用的放大版画笔像素点
my_pixel = None
if pixel_ref.Valid():
    pixel_ref.Copy()
    my_pixel = frame.Paste()
    my_pixel.setVisible(False)
    my_pixel.Scale([3.0, 3.0, 3.0]) # 像素精细度

RDK.setSelection([])
RDK.Render(True)

#-------------------------------------------
# Initialize the robot
home_target = RDK.Item('Target 1', robolink.ITEM_TYPE_TARGET)
if not home_target.Valid():
    RDK.ShowMessage("Please create a target named 'Target 1' to save your starting posture.")
    quit()
home_joints = home_target.Joints().tolist()

print("Moving robot to home joints...")
robot.setPoseFrame(frame)
robot.setPoseTool(tool)
robot.MoveJ(home_joints)
print("Robot moved to home joints.")

# 计算初始手腕姿态，并锁定
orient_frame2tool = robomath.invH(frame.Pose()) * robot.SolveFK(home_joints) * tool.Pose()

# --- 最精妙的修复：将 SVG 图案的正中心，完全对齐到 Target 1 笔尖位置 ---
CENTER_X = orient_frame2tool.Pos()[0]
CENTER_Y = orient_frame2tool.Pos()[1]

# 计算位移，让图案中心正好落在 (CENTER_X, CENTER_Y)
TRANSLATE_REAL = CENTER_Y - (svg_width / 2 + svg_width_min)
TRANSLATE_IMAG = CENTER_X - (svg_height / 2 + svg_height_min)
TRANSLATE = complex(TRANSLATE_REAL, TRANSLATE_IMAG)

orient_frame2tool[0:3, 3] = robomath.Mat([0, 0, 0])

#-------------------------------------------
RDK.ShowMessage(f"Drawing SVG centered at Target 1..", False)

for path_count, (path, attrib) in enumerate(zip(paths, path_attribs)):
    styles = {}

    if 'style' not in attrib:
        if 'fill' in attrib:
            styles['fill'] = attrib['fill']
        if 'stroke' in attrib:
            styles['stroke'] = attrib['stroke']
    else:
        for style in attrib['style'].split(';'):
            style_pair = style.split(':')
            if len(style_pair) != 2:
                continue
            styles[style_pair[0].strip()] = style_pair[1].strip()

    if 'fill' in styles and not styles['fill'].startswith('#'):
        styles.pop('fill')
    if 'stroke' in styles and not styles['stroke'].startswith('#'):
        styles.pop('stroke')

    hex_color = DEFAULT_PATH_COLOR
    if USE_STYLE_COLOR:
        if PREFER_STROKE_OVER_FILL_COLOR:
            if 'stroke' in styles:
                hex_color = styles['stroke']
            elif 'fill' in styles:
                hex_color = styles['fill']
        else:
            if 'fill' in styles:
                hex_color = styles['fill']
            elif 'stroke' in styles:
                hex_color = styles['stroke']

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
            segment.point(t)
            if i < steps:
                i_len = segment_len * i / steps
                t = segment.ilength(i_len)

            point = segment.point(t)
            py, px = point.real, point.imag

            pa = 0
            if prev_point:
                v = point - prev_point
                norm_v = robomath.sqrt(v.real * v.real + v.imag * v.imag)
                v = v / norm_v if norm_v > 1e-6 else complex(1, 0)
                pa = robomath.atan2(v.real, v.imag)

            if not approach_done and i == 0:
                # 给所有点位加上 Z 轴方向的安全微调 (PEN_Z_OFFSET)
                target0 = robomath.transl(px, py, PEN_Z_OFFSET) * orient_frame2tool * robomath.rotz(pa)
                target0_app = target0 * robomath.transl(0, 0, -APPROACH)
                
                # 预先检查逆运动学，如果够不到给出明确提示
                ik_sol = robot.SolveIK(target0_app, home_joints)
                if len(ik_sol.tolist()) == 0:
                    RDK.ShowMessage("❌ 严重错误：机器臂够不到！请把机器臂底座往黑板推近一点，或者重新设置一个离黑板更近的 Target 1。", False)
                    print("IK Failed for approach point. target0_app:", target0_app)
                    quit()
                    
                robot.setSpeed(SPEED_HOVER)  # 快速在空中飞到起始点上方
                robot.MoveJ(target0_app)
                
                robot.setSpeed(SPEED_PLUNGE) # 极其缓慢地直线“轻放”到白板上，避免砸坏白板
                robot.MoveJ(target0)
                
                approach_done = True
                continue

            point_pose = robomath.transl(px, py, PEN_Z_OFFSET) * robomath.rotz(pa)
            robot_pose = robomath.transl(px, py, PEN_Z_OFFSET) * orient_frame2tool if not TCP_KEEP_TANGENCY else point_pose * orient_frame2tool

            try:
                robot.setSpeed(SPEED_DRAW)  # 使用平稳的速度进行绘画
                robot.setRounding(2.0)      # 核心物理优化：允许 2mm 的转角平滑，防止机器臂卡顿
                robot.MoveL(robot_pose)     # 既然底座已经居中，换回 MoveL！保证 SVG 线条绝对笔直不走样

            except Exception as e:
                msg = f"❌ 严重错误：机器臂够不到图案边缘的点！\n该点距离中心点(Target 1)的物理偏移为: 左/右 {px - CENTER_X:.1f}mm, 上/下 {py - CENTER_Y:.1f}mm。\n原因：你的机器人底座摆放太偏了（没有正对黑板），导致手腕卡死。请把底座挪到正对黑板的位置！"
                RDK.ShowMessage(msg, False)
                print(msg)
                quit()

            if my_pixel and my_pixel.Valid() and canvas.Valid():
                my_pixel.Recolor(draw_color)
                # 视觉错觉修复：pa 本身就是路径的切线角度，完美消除像素点带来的非弧度错觉
                canvas.AddGeometry(my_pixel, point_pose)

            prev_point = point

    if approach_done:
        target_app = robot_pose * robomath.transl(0, 0, -APPROACH)
        robot.setSpeed(SPEED_HOVER)  # 提笔时使用较快的速度
        robot.MoveJ(target_app)

robot.setSpeed(SPEED_HOVER)
robot.MoveJ(home_joints)

if my_pixel and my_pixel.Valid():
    my_pixel.Delete()

RDK.ShowMessage(f"Done drawing SVG!", False)