# USD Thumbnail Generator

## Purpose
This script takes a thumbnail image of the given USD file supplied and associates it with the file.

## How it works
Given a USD file to use as the subject of the thumbnail do the following

1. Generate a camera such that the subject is in view
2. Sublayer the subject in the camera
3. Run usdrecord to take a snapshot and store it in `/renders/<input>.0.png`
    - `usdrecord --frames 0:0 --camera ZCamera --imageWidth 2048 --renderer Metal camera.usda <input>.#.png` 
    - ZCamera & camera.usda are generated in step 2
    - Only set up for macOS right now
4. If the file is not a usdz file, assign that image as the usd's thumbnail image
4b. If the file is a usdz file, create a new `<subject_usd_file>_Thumbnail.usda`, assign the image as the thumbnail, and sublayer `<subject_usd_file>.usdz`
5. If --create-usdz-result is passed in, combine all of the files into a usdz, in the case of a usd file it would be the input file and the image. In the case of a usdz file it would be the new usda, the image, and the input usdz


## Usage

`python generate_thumbnail.py <subject_usd_file>`

positional arguments:
  usd_file              The USD file you want to add a thumbnail to. If USDZ is input, a new USD file will be created to wrap the existing one called `<subject_usd_file>_Thumbnail.usd`

optional arguments:
  -h, --help            show this help message and exit
  --create-usdz-result  Returns the resulting files as a new usdz file called `<subject_usd_file>_Thumbnail.usdz`
  --verbose             Prints out the steps as they happen