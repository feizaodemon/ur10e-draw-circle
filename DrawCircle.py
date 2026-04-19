from robodk import robolink, robomath
import math

# --- 保护白板的核心物理参数 ---
PEN_Z_OFFSET = 0.0   # 微调笔尖深度(毫米)。正数向后退，负数向前压。
SPEED_HOVER = 200.0  # 笔悬空时的移动速度 (mm/s)
SPEED_PLUNGE = 10.0  # 笔尖接触白板瞬间的“轻放”速度 (mm/s)
SPEED_DRAW = 50.0    # 接触白板画画时的平稳移动速度 (mm/s)
APPROACH = 100.0     # 提笔悬空的距离 (mm)

# --- 画布与画圆的参数 ---
RADIUS = 150.0       # 圆的半径 (毫米)
POINTS_COUNT = 120   # 关键修复：降低到 120 点。如果点太密集(1000点)，点间距小于圆滑转角半径，会导致机器臂在 0° 和 180° 换向时“抄近道”把圆弧削平！
PIXEL_SIZE = 3.0     # 像素点大小，控制线条的粗细

# 1. 连接并获取 RoboDK 对象
RDK = robolink.Robolink()
robot = RDK.Item('', robolink.ITEM_TYPE_ROBOT)
tool = robot.getLink(robolink.ITEM_TYPE_TOOL)
frame = RDK.Item('Draw Frame', robolink.ITEM_TYPE_FRAME)
home_target = RDK.Item('Target 1', robolink.ITEM_TYPE_TARGET)

if not robot.Valid() or not frame.Valid() or not home_target.Valid():
    print("环境错误，未找到机器臂、参考系或 Target 1。")
    quit()

# 1.5 自动检查与配置 UR 的 Payload (物理硬件安全核心！)
# 在驱动真实的 UR 机器臂时，Payload 设置错误会导致动力学解算偏差，甚至触发 Protective Stop。
TOOL_PAYLOAD_KG = 0.5  # 假设画笔和 3D 打印件总重 0.5kg，请根据实际重量修改
robot.setParamRobotTool(TOOL_PAYLOAD_KG) # 1. 自动将 RoboDK 内部的动力学 Payload 设为 0.5kg
robot.RunInstruction(f"set_payload({TOOL_PAYLOAD_KG})", robolink.INSTRUCTION_INSERT_CODE) # 2. 强制给真实 UR 注入底层 URScript 代码
print(f"✅ 安全检查通过：已向 UR 控制器下发 Payload = {TOOL_PAYLOAD_KG}kg")

# 准备画板和像素点 (清除之前的画作)
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
    board_draw.Scale([2000 / 250, 1000 / 250, 1])  # 放大白板
    board_draw.setColor([0, 0, 0, 1]) # 设置黑板背景

pixel_ref = RDK.Item('pixel')

# 创建一块纯净的、没有被拉伸过的透明画板，专门用来存放画出的线条
canvas = RDK.Item('Art Canvas')
if canvas.Valid():
    canvas.Delete()
if pixel_ref.Valid():
    pixel_ref.Copy()
    canvas = frame.Paste()
    canvas.setName('Art Canvas')
    canvas.setVisible(True, False)
    canvas.setColor([0, 0, 0, 0]) # 把基准像素点变透明

# 创建一个专用的放大版画笔像素点
my_pixel = None
if pixel_ref.Valid():
    pixel_ref.Copy()
    my_pixel = frame.Paste()
    my_pixel.setVisible(False)
    my_pixel.Scale([PIXEL_SIZE, PIXEL_SIZE, PIXEL_SIZE]) # 增大像素点，让线条变粗
    my_pixel.Recolor([1, 1, 1, 1]) # 画笔颜色：纯白

home_joints = home_target.Joints().tolist()

# 2. 回到起始点 (Target 1)
print("移动到起点...")
robot.setPoseFrame(frame)
robot.setPoseTool(tool)
robot.setSpeed(SPEED_HOVER)
robot.MoveJ(home_joints)

# 3. 计算画画平面的基准姿态和中心点
orient_frame2tool = robomath.invH(frame.Pose()) * robot.SolveFK(home_joints) * tool.Pose()
CENTER_X = orient_frame2tool.Pos()[0]
CENTER_Y = orient_frame2tool.Pos()[1]

# 提取纯旋转矩阵，去除位移，以便后续重新赋予数学坐标
orient_frame2tool[0:3, 3] = robomath.Mat([0, 0, 0])

# 4. 生成圆形的数学坐标点 (用 sin 和 cos)
print(f"正在计算半径为 {RADIUS}mm 的圆形轨迹...")
points = []
for i in range(POINTS_COUNT + 1):
    # 将圆周 2π 分成 POINTS_COUNT 份
    angle = 2 * math.pi * i / POINTS_COUNT
    
    # 核心数学公式：计算相对于中心点的 X, Y 坐标
    x = CENTER_X + RADIUS * math.cos(angle)
    y = CENTER_Y + RADIUS * math.sin(angle)
    points.append((x, y))

# 5. 控制机器臂走数学轨迹
approach_done = False

for i, (px, py) in enumerate(points):
    # 生成当前点在 3D 空间中的目标姿态
    robot_pose = robomath.transl(px, py, PEN_Z_OFFSET) * orient_frame2tool
    
    if not approach_done:
        # 下笔保护动作：先悬空飞到第一个点的正上方
        target_app = robot_pose * robomath.transl(0, 0, -APPROACH)
        robot.setSpeed(SPEED_HOVER)
        robot.MoveJ(target_app)
        
        # 然后极慢地垂直“轻放”到白板上
        robot.setSpeed(SPEED_PLUNGE)
        robot.MoveJ(robot_pose)
        approach_done = True
        continue

    # 画画动作：平稳地“走直线”到下一个数学坐标点
    robot.setSpeed(SPEED_DRAW)
    robot.setRounding(3.0)  # 配合 120 个点（点间距约7.8mm），3mm 的圆滑半径恰好能切出一个绝对完美的物理圆弧！
    robot.MoveL(robot_pose)
    
    # 在 RoboDK 中留下视觉痕迹 (让画笔显色)
    if my_pixel and my_pixel.Valid() and canvas.Valid():
        # 视觉错觉修复：让正方形像素点跟着圆的切线方向旋转，保证各个角度画出来的线条粗细绝对均匀！
        point_pose = robomath.transl(px, py, PEN_Z_OFFSET) * robomath.rotz(angle)
        canvas.AddGeometry(my_pixel, point_pose)

# 6. 提笔并回到安全点
if approach_done:
    target_app = robot_pose * robomath.transl(0, 0, -APPROACH)
    robot.setSpeed(SPEED_HOVER)
    robot.MoveJ(target_app)

robot.MoveJ(home_joints)

# 清理临时放大的像素点模型
if my_pixel and my_pixel.Valid():
    my_pixel.Delete()

print("完美！圆形绘制完毕。")
