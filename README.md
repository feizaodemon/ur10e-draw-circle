# UR10e Whiteboard Drawing Project (TUM)

This project contains Python scripts to control a Universal Robots UR10e robotic arm using the RoboDK API. The robot is programmed to draw complex SVG vector graphics or mathematically perfect shapes on a vertical whiteboard.

## Features

- **Kinematic Singularity Avoidance**: Automatically scales and translates drawings to ensure they fit within the UR10e's physical reachability zone on a vertical surface.
- **Hardware-Level Safety**: Incorporates explicit `SPEED_PLUNGE` and `SPEED_HOVER` configurations, along with automated `set_payload` injection to prevent UR Protective Stops caused by torque mismatches.
- **Visual & Physical Smoothing**: Implements continuous corner blending (`robot.setRounding`) for industrial smoothness and eliminates graphic optical illusions (tangential brush rotation).

## File Overview

- **`Draw.py`**: A robust SVG parser and executor. It reads an SVG file (can be generated via Inkscape), mathematically scales it to fit the whiteboard, automatically centers it around `Target 1`, and drives the robot to draw it.
- **`DrawCircle.py`**: A purely mathematical drawing script. Generates a perfect circle using parametric equations (`sin`/`cos`), demonstrating high-precision linear movements (`MoveL`) with fine-tuned corner blending.

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
