#!/usr/bin/env python3

from pxr import Usd, UsdGeom, UsdMedia, Sdf
import sys
import subprocess

if __name__ == "__main__":
    if len(sys.argv) == 2:
        input_file = sys.argv[1]

        # print out extents
        print("Step 1: printing extents")
        subject_stage = Usd.Stage.Open(input_file)
        root_prim = subject_stage.GetDefaultPrim()
        boundable = UsdGeom.Boundable(root_prim)

        if boundable:
            extent_attr = boundable.GetExtentAttr()

            extent = extent_attr.Get()

            print("Extent: ", extent)
        else:
            print("The root prim is not boundable")

        # sublayer existing cameras
        print("Step 2: sublayering")
        stage = Usd.Stage.Open('cameras.usda')
        stage.GetRootLayer().subLayerPaths = [input_file]

        # todo: position camera based on extents...
        stage.GetRootLayer().Save()

        
        # take the snapshot
        print("Step 3: take the snapshot")
        image_name = "image_name" + ".#.png"
        cmd = ['usdrecord', '--frames', '0:0', '--camera', 'ZCamera', '--imageWidth', '2048', '--renderer', 'Metal', 'cameras.usda', image_name]
        subprocess.run(cmd, check=True)

        # Associate the snapshot as the thumbnail
        print("Step 4: associate image")
        mediaAPI = UsdMedia.AssetPreviewsAPI.Apply(root_prim)
        thumbnails = UsdMedia.AssetPreviewsAPI.Thumbnails(defaultImage = Sdf.AssetPath(image_name))
        mediaAPI.SetDefaultThumbnails(thumbnails)
        subject_stage.GetRootLayer().Save()