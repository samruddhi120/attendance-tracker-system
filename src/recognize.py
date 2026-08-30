"""
Recognition: detects every face in a photo - built for GROUP photos, since
a classroom shot has many faces, not one - and matches each against the
embeddings enrolled in SQLite.
"""

import face_recognition

from config import MATCH_THRESHOLD
from db import get_all_embeddings


def recognize_faces(image_path, enrolled_data, upsample=1):
    """
    upsample: pass 2 for wide/far shots (e.g. smart-board captures) where
    faces are small - it catches more faces at the cost of speed.
    """
    image = face_recognition.load_image_file(image_path)
    face_locations = face_recognition.face_locations(image, number_of_times_to_upsample=upsample)
    face_encodings = face_recognition.face_encodings(image, face_locations)

    results = []
    for encoding in face_encodings:
        best_roll_no, best_name, best_distance = None, "Unknown", None

        for roll_no, data in enrolled_data.items():
            distances = face_recognition.face_distance(data["embeddings"], encoding)
            min_distance = min(distances)

            if best_distance is None or min_distance < best_distance:
                best_distance = min_distance
                best_roll_no = roll_no
                best_name = data["name"]

        if best_distance is not None and best_distance <= MATCH_THRESHOLD:
            results.append((best_roll_no, best_name, best_distance))
        else:
            results.append((None, "Unknown", best_distance))

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
