#!/usr/bin/env python3

from pxr import Usd, UsdGeom, UsdMedia, Sdf, Gf, UsdUtils
import subprocess
import math
import os
import sys
import argparse
from pathlib import Path

def parse_args():
    parser = argparse.ArgumentParser(description="This script takes a thumbnail image of the given USD file supplied and associates it with the file.")
    parser.add_argument('usd_file', 
                        type=str, 
                        help='The USD file you want to add a thumbnail to. If USDZ is input, a new USD file will be created to wrap the existing one called <input>_Thumbnail.usd')
    parser.add_argument('--create-usdz-result', 
                        action='store_true',
                        help='Returns the resulting files as a new usdz file called <input>_Thumbnail.usdz')
    parser.add_argument('--verbose', 
                        action='store_true',
                        help='Prints out the steps as they happen')
    return parser.parse_args()

def generate_thumbnail(usd_file, verbose):
    if verbose: 
        print("Step 1: Setting up the camera...")
    
    subject_stage = Usd.Stage.Open(usd_file)
    setup_camera(subject_stage, usd_file)
    
    if verbose:
        print("Step 2: Taking the snapshot...")
    
    Path("renders").mkdir(parents=True, exist_ok=True)

    image_path = os.path.join("renders", create_image_filename(usd_file)).replace("\\", "/")
    image_name = take_snapshot(image_path)

    return image_name

def setup_camera(subject_stage, usd_file):
    camera_stage = create_camera()
    move_camera(camera_stage, subject_stage)
    sublayer_subject(camera_stage, usd_file)

def create_camera():
    stage = Usd.Stage.CreateNew('camera.usda')

    # Set metadata on the stage.
    stage.SetDefaultPrim(stage.DefinePrim('/ThumbnailGenerator', 'Xform'))
    stage.SetMetadata('metersPerUnit', 0.01)

    # Define the "MainCamera" under the "ThumbnailGenerator".
    camera = UsdGeom.Camera.Define(stage, '/ThumbnailGenerator/MainCamera')

    # Set the camera attributes.
    camera.CreateFocalLengthAttr(50)
    camera.CreateFocusDistanceAttr(168.60936)
    camera.CreateFStopAttr(0)
    camera.CreateHorizontalApertureAttr(24)
    camera.CreateHorizontalApertureOffsetAttr(0)
    camera.CreateProjectionAttr("perspective")
    camera.CreateVerticalApertureAttr(24)
    camera.CreateVerticalApertureOffsetAttr(0)
    return stage

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

def take_snapshot(image_name):
    renderer = get_renderer()
    cmd = ['usdrecord', '--camera', 'MainCamera', '--imageWidth', '2048', '--renderer', renderer, 'camera.usda', image_name]
    run_os_specific_usdrecord(cmd)
    os.remove("camera.usda")
    return image_name.replace(".#.", ".0.")

def get_renderer():
    if os.name == 'nt':
        print("windows default renderer GL being used...")
        return "GL"
    else:
        if sys.platform == 'darwin':
            print("macOS default renderer Metal being used...")
            return 'Metal'
        else:
            print("linux default renderer GL being used...")
            return 'GL'

def run_os_specific_usdrecord(cmd):
    if os.name == 'nt':
        subprocess.run(cmd, check=True, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    else:
        if sys.platform == 'darwin':
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        else:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)

def create_image_filename(input_path):
    return input_path.split('.')[0] + ".png"

def link_image_to_subject(subject_stage, image_name):
    subject_root_prim = subject_stage.GetDefaultPrim()
    mediaAPI = UsdMedia.AssetPreviewsAPI.Apply(subject_root_prim)
    thumbnails = UsdMedia.AssetPreviewsAPI.Thumbnails(defaultImage = Sdf.AssetPath(image_name))
    mediaAPI.SetDefaultThumbnails(thumbnails)
    subject_stage.GetRootLayer().Save()
    
def create_usdz_wrapper_stage(usdz_file):
    file_name = usdz_file.split('.')[0]
    existing_stage = Usd.Stage.Open(usd_file)
    new_stage = Usd.Stage.CreateNew(file_name + '_Thumbnail.usda')
    
    UsdUtils.CopyLayerMetadata(existing_stage.GetRootLayer(), new_stage.GetRootLayer())

    new_stage.GetRootLayer().subLayerPaths = [usdz_file]
    new_stage.GetRootLayer().Save()
    return new_stage

def zip_results(usd_file, image_name, is_usdz):
    file_list = [usd_file, image_name]

    if is_usdz:
        file_list.append(usd_file.split('.')[0] + '_Thumbnail.usda')
        
    usdz_file = usd_file.split('.')[0] + '_Thumbnail.usdz'
    cmd = ["usdzip", "-r", usdz_file] + file_list
    subprocess.run(cmd)

if __name__ == "__main__":

    args = parse_args()

    usd_file = args.usd_file
    is_usdz = ".usdz" in usd_file
        
    image_name = generate_thumbnail(usd_file, args.verbose)
    subject_stage = create_usdz_wrapper_stage(usd_file) if is_usdz else Usd.Stage.Open(usd_file)

    if args.verbose:
        print("Step 3: Linking thumbnail to subject...")

    link_image_to_subject(subject_stage, image_name)

    if args.create_usdz_result:
        if args.verbose:
            print("Step 4: Linking thumbnail to subject...")
        
        zip_results(usd_file, image_name, is_usdz)