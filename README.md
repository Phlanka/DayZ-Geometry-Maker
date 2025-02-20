# DayZ Geometry Maker for Blender

A Blender addon that simplifies the creation of DayZ mod geometries and memory points. This tool allows modders to set up their model's collision boxes, view geometries, and memory points directly in Blender instead of using DayZ's Object Builder.

## Quick Start Video Tutorial
[![DayZ Geometry Maker Tutorial](https://img.youtube.com/vi/mwhIp50wccA/0.jpg)](https://youtu.be/mwhIp50wccA)

## Features

- Create all required geometry types:
  - Basic Geometry (collision with autocenter)
  - View Geometry (object visibility)
  - Fire Geometry (bullet collision)
- Set up Memory Points:
  - Bounding Box Points (min/max)
  - Center and Radius Points
  - Bullet Travel Points
  - Bolt Axis Points
  - Bullet Ejection Points
  - Eye ADS Point
  - Custom Invview Point
- Create LOD Levels:
  - LOD 1 (Original high-poly model)
  - LOD 2 (Optimized with merged vertices)
  - LOD 3 (Further optimized for distance)
  - LOD 4 (Highly optimized for far distance)

## Installation

1. Download the `create_geometry.py` file
2. Open Blender
3. Go to Edit > Preferences > Add-ons
4. Click "Install" and select the downloaded file
5. Enable the addon by checking the box

## Usage

1. Import your model into Blender
2. Open the Tool panel in the 3D View (press N if not visible)
3. Find the "Create DayZ Geometry" section
4. Select your model in the object picker
5. Create geometries:
   - Click "Create Geometry" for basic collision
   - Click "Create View Geometry" for visibility
   - Click "Create Fire Geometry" for bullet collision
6. Set up memory points:
   - Click "Create Memory" to show options
   - Select which points you want to create
   - Click "Create Selected Memory Points"
7. Create LOD levels:
   - Click "Levels of Detail" to show options
   - Select which LOD levels you want
   - Click "Create Selected LODs"

## Memory Points Explained

- **Default Points**:
  - boundingbox_min/max: Define object bounds
  - invview: Camera position for inventory view
- **Center Point**: Object's center of mass
- **Radius Point**: Collision radius reference
- **Bullet Travel Points**: Define bullet trajectory
- **Bolt Axis Points**: Define bolt movement path
- **Bullet Eject Points**: Define casing ejection path
- **Eye ADS Point**: Defines aiming position

## LOD System

The addon creates optimized versions of your model for different view distances:
- **1**: Original high-quality mesh
- **2**: Slightly optimized (merged vertices at 0.00212 distance)
- **3**: Medium optimization (merged vertices at 0.00424 distance)
- **4**: High optimization (merged vertices at 0.00848 distance)

## Benefits Over Object Builder

- Direct visualization in Blender
- Faster workflow
- More precise point placement
- Better integration with modeling process
- Automatic calculations for geometry sizes
- One-click LOD creation

## Requirements

- Blender 4.0 or newer
- Basic understanding of DayZ modding concepts

## Contributing

Feel free to contribute to this project by:
- Reporting issues
- Suggesting improvements
- Submitting pull requests

## Credits

Created by [Phlanka.com](https://phlanka.com)

## Support

Join our Discord community: [http://discord.phlanka.com](http://discord.phlanka.com)

## License

This project is open source and available under the [MIT License](LICENSE). 