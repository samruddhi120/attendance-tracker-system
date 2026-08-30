"""
Streamlit UI for the attendance system - three tabs:
  - Take Attendance: upload a group photo, review/correct each detected
    face (and manually add anyone missed) before saving, then export
  - Enroll Student: upload photos for a new student, straight into SQLite
  - View Report: browse a day's full roster (Present + Absent) and
    download the Excel workbook

Run with:
    streamlit run app.py
"""

import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import streamlit as st
import pandas as pd
import numpy as np
import cv2
from PIL import Image

from config import ENROLLMENT_DIR, MASTER_WORKBOOK, MATCH_THRESHOLD
from db import init_db, get_all_embeddings, get_attendance_for_date, get_all_students
from recognize import recognize_faces
from attendance_logger import mark_present
from excel_writer import export_day
from enroll import enroll_student

st.set_page_config(page_title="Attendance System", layout="wide")
init_db()

if "review" not in st.session_state:
    st.session_state.review = None
if "review_id" not in st.session_state:
    st.session_state.review_id = 0

st.title("Face Recognition Attendance System")

tab_attendance, tab_enroll, tab_report = st.tabs(
    ["Take Attendance", "Enroll Student", "View Report"]
)

# ---------------------------------------------------------------- Attendance
with tab_attendance:
    st.subheader("Mark attendance from a group photo")

    session_date = st.date_input("Session date", value=datetime.now(), key="session_date")
    session_date_str = session_date.strftime("%Y-%m-%d")

    source = st.radio("Photo source", ["phone", "smartboard"], horizontal=True)
    uploaded_photo = st.file_uploader(
        "Upload a group photo", type=["jpg", "jpeg", "png"], key="attendance_photo"
    )

    # ---- Step 1: detect ----
    if uploaded_photo is not None and st.session_state.review is None:
        temp_path = os.path.join("data", "raw_uploads", uploaded_photo.name)
        os.makedirs(os.path.dirname(temp_path), exist_ok=True)
        with open(temp_path, "wb") as f:
            f.write(uploaded_photo.getbuffer())

        if st.button("Detect Faces"):
            enrolled_data = get_all_embeddings()
            if not enrolled_data:
                st.error("No students enrolled yet - use the Enroll Student tab first.")
            else:
                upsample = 2 if source == "smartboard" else 1
                with st.spinner("Detecting and recognizing faces..."):
                    results, locations = recognize_faces(temp_path, enrolled_data, upsample=upsample)

                st.session_state.review_id += 1
                st.session_state.review = {
                    "id": st.session_state.review_id,
                    "image_path": temp_path,
                    "source": source,
                    "session_date": session_date_str,
                    "faces": [
                        {"location": loc, "matched_roll_no": r, "matched_name": n, "distance": d}
                        for loc, (r, n, d) in zip(locations, results)
                    ],
                }
                st.rerun()

    # ---- Step 2: review, correct, and confirm ----
    review = st.session_state.review
    if review is not None:
        enrolled_data = get_all_embeddings()
        rid = review["id"]

        img_array = np.array(Image.open(review["image_path"]).convert("RGB"))

        # Full annotated overview - green if a face currently has a confident
        # match, red if it's Unknown / below threshold.
        annotated = img_array.copy()
        for face in review["faces"]:
            top, right, bottom, left = face["location"]
            confident = face["matched_roll_no"] and face["distance"] is not None and face["distance"] <= MATCH_THRESHOLD
            color = (0, 200, 0) if confident else (200, 0, 0)
            label = f"{face['matched_name']} ({face['matched_roll_no']})" if confident else "Unknown"
            cv2.rectangle(annotated, (left, top), (right, bottom), color, 2)
            cv2.putText(annotated, label, (left, max(top - 10, 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        st.image(annotated, caption=f"{len(review['faces'])} face(s) detected", use_container_width=True)

        if not review["faces"]:
            st.warning("No faces detected in this photo at all - use manual marking below, or rescan with a clearer photo.")

        option_labels = ["Unknown / Not a student"] + [f"{d['name']} ({r})" for r, d in enrolled_data.items()]
        label_to_id = {"Unknown / Not a student": (None, None)}
        for r, d in enrolled_data.items():
            label_to_id[f"{d['name']} ({r})"] = (r, d["name"])

        st.markdown("#### Review each detected face")
        st.caption("Correct any wrong or missing matches before saving - nothing is written to the database yet.")

        selections = []
        for i, face in enumerate(review["faces"]):
            top, right, bottom, left = face["location"]
            crop = img_array[max(top, 0):bottom, max(left, 0):right]

            confident = face["matched_roll_no"] and face["distance"] is not None and face["distance"] <= MATCH_THRESHOLD
            default_label = f"{face['matched_name']} ({face['matched_roll_no']})" if confident else "Unknown / Not a student"
            default_index = option_labels.index(default_label) if default_label in option_labels else 0

            col1, col2 = st.columns([1, 3])
            with col1:
                if crop.size > 0:
                    st.image(crop, width=100)
            with col2:
                chosen = st.selectbox(
                    f"Face {i + 1}"
                    + (f" (distance {face['distance']:.2f})" if face["distance"] is not None else ""),
                    options=option_labels,
                    index=default_index,
                    key=f"face_select_{rid}_{i}",
                )
            selections.append(chosen)

        selected_roll_nos = {label_to_id[s][0] for s in selections if label_to_id[s][0]}
        missing_students = [(r, d["name"]) for r, d in enrolled_data.items() if r not in selected_roll_nos]

        manual_selected_labels = []
        if missing_students:
            st.markdown("#### Not detected - add manually if they were actually present")
            missing_options = [f"{name} ({r})" for r, name in sorted(missing_students, key=lambda x: x[1])]
            manual_selected_labels = st.multiselect(
                "Select students to mark present",
                options=missing_options,
                key=f"manual_add_{rid}",
            )

        col_save, col_rescan = st.columns(2)
        with col_rescan:
            if st.button("Rescan / Upload Different Photo"):
                st.session_state.review = None
                st.rerun()

        with col_save:
            if st.button("Confirm & Save Attendance", type="primary"):
                newly_marked = []

                for label in selections:
                    roll_no, name = label_to_id[label]
                    if roll_no:
                        if mark_present(roll_no, name, review["source"], review["session_date"]):
                            newly_marked.append((roll_no, name))

                for label in manual_selected_labels:
                    name_part, roll_part = label.rsplit(" (", 1)
                    roll_no = roll_part.rstrip(")")
                    if mark_present(roll_no, name_part, "manual", review["session_date"]):
                        newly_marked.append((roll_no, name_part))

                export_day(review["session_date"])

                st.success(
                    f"Saved. {len(newly_marked)} student(s) newly marked present for {review['session_date']}."
                )
                st.session_state.review = None
                st.rerun()

# ------------------------------------------------------------------- Enroll
with tab_enroll:
    st.subheader("Enroll a new student")

    roll_no = st.text_input("Roll number")
    name = st.text_input("Full name")
    photos = st.file_uploader(
        "Upload multiple photos (different angles/expressions work best)",
        type=["jpg", "jpeg", "png"],
        accept_multiple_files=True,
        key="enroll_photos",
    )

    if st.button("Enroll student"):
        if not roll_no or not name or not photos:
            st.error("Roll number, name, and at least one photo are required.")
        else:
            folder_name = f"{roll_no}_{name.replace(' ', '_')}"
            folder_path = os.path.join(ENROLLMENT_DIR, folder_name)
            os.makedirs(folder_path, exist_ok=True)

            for photo in photos:
                with open(os.path.join(folder_path, photo.name), "wb") as f:
                    f.write(photo.getbuffer())

            with st.spinner("Generating embeddings..."):
                count = enroll_student(roll_no, name, folder_path)

            if count:
                st.success(f"Enrolled {name} ({roll_no}) with {count} photo(s).")
            else:
                st.error("No usable faces found in the uploaded photos - try clearer, front-facing shots.")

# ------------------------------------------------------------------- Report
with tab_report:
    st.subheader("Attendance report")

    selected_date = st.date_input("Date", value=datetime.now())
    date_str = selected_date.strftime("%Y-%m-%d")

    present_rows = {row[0]: row for row in get_attendance_for_date(date_str)}
    all_students = get_all_students()

    if all_students:
        roster = []
        for roll_no, name in all_students:
            if roll_no in present_rows:
                roster.append(present_rows[roll_no])
            else:
                roster.append((roll_no, name, date_str, "", "Absent", "-"))

        df = pd.DataFrame(roster, columns=["Roll No", "Name", "Date", "Time", "Status", "Source"])

        present_count = (df["Status"] == "Present").sum()
        col1, col2 = st.columns(2)
        col1.metric("Present", int(present_count))
        col2.metric("Absent", len(df) - int(present_count))

        st.dataframe(df, use_container_width=True)
    else:
        st.info("No students enrolled yet - use the Enroll Student tab first.")

    if os.path.exists(MASTER_WORKBOOK):
        with open(MASTER_WORKBOOK, "rb") as f:
            st.download_button(
                "Download master workbook",
                data=f.read(),
                file_name="master_attendance.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
