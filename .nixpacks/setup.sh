#!/bin/bash

# Set environment variables for OpenCV headless operation
export OPENCV_HEADLESS=1
export LIBGL_ALWAYS_SOFTWARE=1
export LIBGL_ALWAYS_INDIRECT=1
export QT_QPA_PLATFORM=offscreen
export MPLBACKEND=Agg
export OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS=0

# Print confirmation
echo "Environment variables set for headless OpenCV operation"

# Make sure pip is up to date
pip install --upgrade pip setuptools wheel

echo "Setup phase completed successfully"