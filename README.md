# UR10e Whiteboard Drawing Project (TUM)

This project contains Python scripts to control a Universal Robots UR10e robotic arm using the RoboDK API. The robot is programmed to draw complex SVG vector graphics or mathematically perfect shapes on a vertical whiteboard.

## Features

- **Kinematic Singularity Avoidance**: Automatically scales and translates drawings to ensure they fit within the UR10e's physical reachability zone on a vertical surface.
- **Hardware-Level Safety**: Incorporates explicit `SPEED_PLUNGE` and `SPEED_HOVER` configurations, along with automated `set_payload` injection to prevent UR Protective Stops caused by torque mismatches.
- **Visual & Physical Smoothing**: Implements continuous corner blending (`robot.setRounding`) for industrial smoothness and eliminates graphic optical illusions (tangential brush rotation).

## File Overview

- **`Draw.py`**: A robust SVG parser and executor. It reads an SVG file (can be generated via Inkscape), mathematically scales it to fit the whiteboard, automatically centers it around `Target 1`, and drives the robot to draw it.
- **`DrawCircle.py`**: A mathematical circle drawing script. It generates a circle around `Target 1` and uses circular interpolation (`MoveC`) for smoother execution on the robot.

## Prerequisites & Installation

> [!WARNING]  
> Due to the lack of pre-compiled wheels for `ur_rtde` on Python 3.13+, it is **highly recommended** to use **Python 3.11 or 3.12** for this project to avoid complex C++ compilation errors on Windows.

1. Create and activate a Python virtual environment:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
2. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```

## RoboDK Station Setup

To run these scripts in simulation or online, your RoboDK station must contain the following named items:
- `UR10e` (The robot arm)
- `Draw Frame` (The reference frame for the whiteboard)
- `Target 1` (The home/center resting position taught in a neutral, non-extended posture)
- `Drawing Board` (The black canvas background)
- `pixel` (A 1mm reference cube used as the digital ink drop)

## Inkscape SVG Workflow

When using your own SVG artwork with `Draw.py`:
1. Open Inkscape and create your artwork.
2. Select all objects (`Ctrl + A`).
3. Navigate to **Path -> Object to Path** and **Path -> Stroke to Path**. (The robot only understands vector paths, not text or layers).
4. Save as a standard `.svg` file.
5. Run `Draw.py` and select your file in the prompt.

## Simulation And Real Robot Modes

Both `Draw.py` and `DrawCircle.py` expose the same top-level switches:

- `REAL_ROBOT`
- `DRY_RUN`

Recommended usage:

1. **RoboDK simulation only**
   ```python
   REAL_ROBOT = False
   DRY_RUN = False
   ```
2. **First test on the real UR10e**
   ```python
   REAL_ROBOT = True
   DRY_RUN = True
   ```
3. **After dry-run validation on the real UR10e**
   ```python
   REAL_ROBOT = True
   DRY_RUN = False
   ```

When `REAL_ROBOT = True` and `DRY_RUN = True`, the scripts automatically switch to safer first-pass parameters such as:

- reduced drawing speed
- reduced drawing size
- positive `PEN_Z_OFFSET` to keep the tip off the board initially

## UR10e Sim-to-Real Checklist

Follow this order when moving from RoboDK simulation to the physical UR10e:

1. Pull the latest repository version and create the `.venv` environment.
2. Open the RoboDK station and confirm these item names still exist:
   - `Draw Frame`
   - `Target 1`
   - `Whiteboard 250mm`
   - `pixel`
3. Measure the real tool and update `TOOL_PAYLOAD_KG` in both scripts.
4. Recalibrate the tool TCP so the TCP matches the real pen tip.
5. Recalibrate `Draw Frame` so it matches the physical whiteboard plane.
6. Re-teach `Target 1` as a safe, reachable start pose.
7. Set `REAL_ROBOT = True` and `DRY_RUN = True`.
8. Run `DrawCircle.py` first, not `Draw.py`.
9. Verify the robot can reach the path safely without touching the board.
10. Reduce `PEN_Z_OFFSET` gradually until the pen just starts touching the board.
11. Validate a small circle before running larger drawings or SVG artwork.
12. Once the dry-run and contact test are stable, switch to:
    ```python
    REAL_ROBOT = True
    DRY_RUN = False
    ```
13. Run a final small-circle test again.
14. Only then run `Draw.py` with a simple SVG.

## Recommended First Real-Robot Parameters

For the first physical test, start from the centralized configuration block near the top of each script and verify:

- `TOOL_PAYLOAD_KG` matches the real hardware mass
- `PEN_Z_OFFSET` is still conservative
- `SPEED_HOVER`, `SPEED_PLUNGE`, and `SPEED_DRAW` are low enough for safe testing

Suggested validation order:

1. TCP
2. `Draw Frame`
3. `Target 1`
4. `TOOL_PAYLOAD_KG`
5. `PEN_Z_OFFSET`
6. drawing speeds
7. drawing size

Do not start by tuning path density or smoothing if TCP or frame calibration is still wrong.
