"""
Standalone detection test/debug script. Not part of the main pipeline -
use this to sanity-check face detection on a single photo (especially
group photos and wide smart-board shots) and see the boxes drawn.

Usage: python src/detect.py <image_path>
"""

import sys
import os

import face_recognition
import cv2

from config import OUTPUTS_DIR


def detect_faces(image_path, upsample=1):
    image = face_recognition.load_image_file(image_path)
    face_locations = face_recognition.face_locations(image, number_of_times_to_upsample=upsample)
    print(f"Found {len(face_locations)} face(s) in this photo.")
    return face_locations, image


if __name__ == "__main__":
    image_path = sys.argv[1] if len(sys.argv) > 1 else "data/test_photos/phone/group1.png"

    locations, image = detect_faces(image_path)
    image_bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

    for (top, right, bottom, left) in locations:
        cv2.rectangle(image_bgr, (left, top), (right, bottom), (0, 255, 0), 2)

    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUTS_DIR, "detected_faces.jpg")
    cv2.imwrite(out_path, image_bgr)
    print(f"Saved result to {out_path}")
