"""
Recognition: detects every face in a photo - built for GROUP photos, since
a classroom shot has many faces, not one - and matches each against the
embeddings enrolled in SQLite.
"""

import cv2
import face_recognition

from config import MATCH_THRESHOLD, SMALL_FACE_WIDTH, SMALL_FACE_MATCH_THRESHOLD
from db import get_all_embeddings

FAR_TILE_TARGET_WIDTH = 1920  # each tile is enlarged to roughly this width before detection


def _iou(a, b):
    top, right, bottom, left = max(a[0], b[0]), min(a[1], b[1]), min(a[2], b[2]), max(a[3], b[3])
    inter = max(0, right - left) * max(0, bottom - top)
    area_a = (a[2] - a[0]) * (a[1] - a[3])
    area_b = (b[2] - b[0]) * (b[1] - b[3])
    return inter / (area_a + area_b - inter) if inter else 0.0


def _tile_starts(length, tile, step):
    if length <= tile:
        return [0]
    return list(range(0, length - tile, step)) + [length - tile]


def _detect_far_faces(image):
    """
    The HOG detector can't see faces much smaller than ~80px, which is what
    people in the back rows of a classroom photo are. Scan overlapping tiles
    enlarged to ~1920px wide so those small faces become detectable, and map
    the hits back to the original image's coordinates.
    """
    height, width = image.shape[:2]
    tile_w = max(640, -(-width // 3))
    tile_h = max(360, -(-height // 3))
    scale = FAR_TILE_TARGET_WIDTH / tile_w

    found = []
    for y0 in _tile_starts(height, tile_h, int(tile_h * 0.75)):
        for x0 in _tile_starts(width, tile_w, int(tile_w * 0.75)):
            tile = image[y0:y0 + tile_h, x0:x0 + tile_w]
            enlarged = cv2.resize(tile, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
            for top, right, bottom, left in face_recognition.face_locations(enlarged, number_of_times_to_upsample=1):
                found.append((
                    y0 + int(top / scale), x0 + int(right / scale),
                    y0 + int(bottom / scale), x0 + int(left / scale),
                ))
    return found


def recognize_faces(image_path, enrolled_data, upsample=1, far_pass=True):
    """
    upsample: pass 2 for wide/far shots (e.g. smart-board captures) where
    faces are small - it catches more faces at the cost of speed.
    far_pass: also scan enlarged tiles for small, distant faces (back rows)
    the normal pass misses. Faces found this way that match nobody come back
    as Unknown, like any other unrecognized face.
    """
    image = face_recognition.load_image_file(image_path)
    face_locations = face_recognition.face_locations(image, number_of_times_to_upsample=upsample)
    if far_pass:
        for loc in _detect_far_faces(image):
            if all(_iou(loc, existing) < 0.3 for existing in face_locations):
                face_locations.append(loc)
    face_encodings = face_recognition.face_encodings(image, face_locations)

    results = []
    for encoding, (top, right, bottom, left) in zip(face_encodings, face_locations):
        best_roll_no, best_name, best_distance = None, "Unknown", None

        for roll_no, data in enrolled_data.items():
            distances = face_recognition.face_distance(data["embeddings"], encoding)
            min_distance = min(distances)

            if best_distance is None or min_distance < best_distance:
                best_distance = min_distance
                best_roll_no = roll_no
                best_name = data["name"]

        # Tiny faces give unreliable embeddings, so they must match much more closely.
        threshold = SMALL_FACE_MATCH_THRESHOLD if (right - left) < SMALL_FACE_WIDTH else MATCH_THRESHOLD
        if best_distance is not None and best_distance <= threshold:
            results.append((best_roll_no, best_name, best_distance))
        else:
            results.append((None, "Unknown", best_distance))

    # A student can only be in a photo once: if two faces matched the same
    # student, the closer match keeps them and the other becomes Unknown.
    closest = {}
    for i, (roll_no, _name, distance) in enumerate(results):
        if roll_no is not None and (roll_no not in closest or distance < results[closest[roll_no]][2]):
            closest[roll_no] = i
    for i, (roll_no, _name, distance) in enumerate(results):
        if roll_no is not None and closest[roll_no] != i:
            results[i] = (None, "Unknown", distance)

    return results, face_locations


if __name__ == "__main__":
    enrolled_data = get_all_embeddings()
    image_path = "data/test_photos/phone/test1.png"

    results, locations = recognize_faces(image_path, enrolled_data)

    for roll_no, name, distance in results:
        label = f"{name} ({roll_no})" if roll_no else name
        if distance is not None:
            print(f"{label} - distance: {distance:.3f}")
        else:
            print(label)
