# USD Thumbnail Generator

## Purpose
Create a script that can be run to produce a thumbnail image and associate that with a USD file

## How it works
Given a cameras.usd file that lists one or more camera angles, along with a given USD file to use as the subject of the thumbnail do the following

1. Sublayer the subject in the cameras.usd file
2. Set the camera position and orientation such that the extents are in the view of the camera
3. Run usdrecord to generate an image
4. Associate that image with the subject usd file


## Usage

`python3 generate_thumbnail.py <subject_usd_file>`

## Things to do

1. Calculate camera position from extents properly
2. Support different camera angles (add these params to the command line arguments)
3. Is anything special needed for usdz?
4. Renderer and other usdrecord commands are hardcoded, could also be command line arguments