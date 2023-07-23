#!/usr/bin/env python3

from pxr import Usd, UsdGeom, UsdMedia, Sdf, Gf
import sys
import subprocess
import math

def setup_camera(subject_stage):
    camera_stage = Usd.Stage.Open('cameras.usda')
    move_camera(camera_stage, subject_stage)
    sublayer_subject(camera_stage, input_file)

def move_camera(camera_stage, subject_stage):
    camera_prim = UsdGeom.Camera.Get(camera_stage, '/ThumbnailGenerator/MainCamera')
    camera_translation = create_camera_translation(subject_stage, camera_prim)
    apply_camera_translation(camera_stage, camera_prim, camera_translation)

def create_camera_translation(subject_stage, camera_prim):
    bounding_box = get_bounding_box(subject_stage)
    min_bound = bounding_box.GetMin()
    max_bound = bounding_box.GetMax()

    subject_center = (min_bound + max_bound) / 2.0
    distance = get_distance_to_camera(min_bound, max_bound, camera_prim)
    return subject_center + get_camera_z_translation(distance)

def get_bounding_box(subject_stage):
    bboxCache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_])
    # Compute the bounding box for all geometry under the root
    root = subject_stage.GetPseudoRoot()
    return bboxCache.ComputeWorldBound(root).GetBox()

def get_distance_to_camera(min_bound, max_bound, camera_prim):
    focal_length = camera_prim.GetFocalLengthAttr().Get()
    horizontal_aperture = camera_prim.GetHorizontalApertureAttr().Get()
    vertical_aperture = camera_prim.GetVerticalApertureAttr().Get()

    distance_to_capture_horizontal = calculate_field_of_view_distance(horizontal_aperture, (max_bound[0] - min_bound[0]) * 10, focal_length)
    distance_to_capture_vertical = calculate_field_of_view_distance(vertical_aperture, (max_bound[1] - min_bound[1]) * 10, focal_length)

    return max(distance_to_capture_horizontal, distance_to_capture_vertical)

def calculate_field_of_view_distance(sensor_size, object_size, focal_length):
    return calculate_camera_distance(object_size, calculate_field_of_view(focal_length, sensor_size))
    
def calculate_field_of_view(focal_length, sensor_size):
    # Focal length and sensor size should be in the same units (e.g., mm)
    field_of_view = 2 * math.atan(sensor_size / (2 * focal_length))
    return field_of_view

def calculate_camera_distance(subject_size, field_of_view):
    # Subject size and field of view should be in the same units (e.g., mm and degrees)
    distance = (subject_size / 2) / math.tan(field_of_view / 2)
    return distance

def get_camera_z_translation(distance):
    return Gf.Vec3d(0, 0, distance / 10.0)  # convert units from mm to cm

def apply_camera_translation(camera_stage, camera_prim, camera_translation):
    xformRoot = UsdGeom.Xformable(camera_prim.GetPrim())
    translateOp = None
    # Go through each operation in the xformable schema
    for op in xformRoot.GetOrderedXformOps():
        # If the operation is a translate operation, we've found our operation
        if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
            translateOp = op
            break

    # If no translate operation exists, create one
    if translateOp is None:
        translateOp = xformRoot.AddTranslateOp(UsdGeom.XformOp.PrecisionDouble)

    translateOp.Set(camera_translation)
    camera_stage.Save()

def sublayer_subject(camera_stage, input_file):
    camera_stage.GetRootLayer().subLayerPaths = [input_file]
    camera_stage.GetRootLayer().Save()

def take_snapshot(input_file):
    image_name = input_file.split('.')[0] + ".#.png"
    cmd = ['usdrecord', '--frames', '0:0', '--camera', 'ZCamera', '--imageWidth', '2048', '--renderer', 'Metal', 'cameras.usda', image_name]
    subprocess.run(cmd, check=True)
    return image_name

def link_image_to_subject(subject_stage, image_name):
    subject_root_prim = subject_stage.GetDefaultPrim()
    mediaAPI = UsdMedia.AssetPreviewsAPI.Apply(subject_root_prim)
    thumbnails = UsdMedia.AssetPreviewsAPI.Thumbnails(defaultImage = Sdf.AssetPath(image_name))
    mediaAPI.SetDefaultThumbnails(thumbnails)
    subject_stage.GetRootLayer().Save()

if __name__ == "__main__":
    if len(sys.argv) == 2:
        input_file = sys.argv[1]

        print("Thumbnail Generation for: ", input_file)

        print("Step 1: Setting up the camera...")
        subject_stage = Usd.Stage.Open(input_file)
        setup_camera(subject_stage)
        
        print("Step 2: Taking the snapshot...")
        image_name = take_snapshot(input_file)

        print("Step 3: Linking thumbnail to subject...")
        link_image_to_subject(subject_stage, image_name)
        