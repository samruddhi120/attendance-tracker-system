"""
Streamlit UI for the attendance system - three tabs:
  - Take Attendance: upload a group photo, detect + recognize + log + export
  - Enroll Student: upload photos for a new student, straight into SQLite
  - View Report: browse a day's attendance and download the Excel workbook

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

from config import ENROLLMENT_DIR, MASTER_WORKBOOK
from db import init_db, get_all_embeddings, get_attendance_for_date
from recognize import recognize_faces
from attendance_logger import process_photo
from excel_writer import export_day
from enroll import enroll_student

st.set_page_config(page_title="Attendance System", layout="wide")
init_db()

st.title("Face Recognition Attendance System")

tab_attendance, tab_enroll, tab_report = st.tabs(
    ["Take Attendance", "Enroll Student", "View Report"]
)

# ---------------------------------------------------------------- Attendance
with tab_attendance:
    st.subheader("Mark attendance from a group photo")

    source = st.radio("Photo source", ["phone", "smartboard"], horizontal=True)
    uploaded_photo = st.file_uploader(
        "Upload a group photo", type=["jpg", "jpeg", "png"], key="attendance_photo"
    )

    if uploaded_photo is not None:
        temp_path = os.path.join("data", "raw_uploads", uploaded_photo.name)
        os.makedirs(os.path.dirname(temp_path), exist_ok=True)
        with open(temp_path, "wb") as f:
            f.write(uploaded_photo.getbuffer())

        if st.button("Run detection + mark attendance"):
            enrolled_data = get_all_embeddings()
            if not enrolled_data:
                st.error("No students enrolled yet - use the Enroll Student tab first.")
            else:
                upsample = 2 if source == "smartboard" else 1

                with st.spinner("Detecting and recognizing faces..."):
                    results, locations = recognize_faces(temp_path, enrolled_data, upsample=upsample)

                    # Draw boxes + labels for a visual result. Green = recognized, red = unknown.
                    annotated = np.array(Image.open(temp_path).convert("RGB"))
                    for (top, right, bottom, left), (roll_no, name, _distance) in zip(locations, results):
                        color = (0, 200, 0) if roll_no else (200, 0, 0)
                        label = f"{name} ({roll_no})" if roll_no else name
                        cv2.rectangle(annotated, (left, top), (right, bottom), color, 2)
                        cv2.putText(
                            annotated, label, (left, max(top - 10, 10)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2,
                        )

                    st.image(annotated, caption="Detected faces", use_container_width=True)

                    # Re-runs recognition once more inside process_photo to actually
                    # write to the DB - simpler to keep display and logging separate
                    # than thread partial state between them, and it's fast at this scale.
                    marked, already_marked, unknown_count = process_photo(
                        temp_path, source, enrolled_data, upsample=upsample
                    )

                col1, col2, col3 = st.columns(3)
                col1.metric("Newly marked", len(marked))
                col2.metric("Already marked today", len(already_marked))
                col3.metric("Unrecognized faces", unknown_count)

                if marked:
                    st.success("Marked: " + ", ".join(f"{n} ({r})" for r, n in marked))
                if already_marked:
                    st.info("Already marked today: " + ", ".join(f"{n} ({r})" for r, n in already_marked))

                export_day(datetime.now().strftime("%Y-%m-%d"))
                st.caption("Excel report updated.")

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

    rows = get_attendance_for_date(date_str)
    if rows:
        df = pd.DataFrame(rows, columns=["Roll No", "Name", "Date", "Time", "Status", "Source"])
        st.dataframe(df, use_container_width=True)
    else:
        st.info(f"No attendance recorded for {date_str} yet.")

    if os.path.exists(MASTER_WORKBOOK):
        with open(MASTER_WORKBOOK, "rb") as f:
            st.download_button(
                "Download master workbook",
                data=f.read(),
                file_name="master_attendance.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
