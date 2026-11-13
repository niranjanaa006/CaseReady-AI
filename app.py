import streamlit as st
from PIL import Image
import io
import os
import json
from datetime import datetime
import pandas as pd

from radiology_engine import analyze_image
import database
import pdf_generator

# --- Initialize Database ---
database.init_db()

# --- Page Configuration ---
st.set_page_config(
    page_title="CaseReady AI - Clinical Radiology & Learning Workstation",
    page_icon="🩻",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Top-Level Safety Banner ---
st.caption(
    "⚠️ **Investigational Prototype:** CaseReady AI is an educational decision-support tool. "
    "It does not provide verified diagnostic evaluation or treatment prescription. "
    "All findings require qualified board-certified radiologist verification."
)

# --- Sidebar Navigation & Configuration ---
with st.sidebar:
    st.image(
        "https://images.unsplash.com/photo-1516549655169-df83a0774514?w=500&auto=format&fit=crop&q=60",
        caption="CaseReady AI Workstation",
        use_container_width=True,
    )
    st.title("CaseReady AI")
    st.markdown("**Radiology Workflow & Learning**")
    
    navigation = st.radio(
        "Workstation Navigation:",
        options=[
            "🩺 Reading Room (Analyze & Compare)",
            "📋 Worklist & Case Archive",
            "📚 Case-Based Learning Library",
            "🎓 Student Learning Center",
            "📊 AI Evaluation & Performance",
        ],
        index=0,
    )

    st.divider()
    st.markdown("**Engine Settings:**")
    selected_model = st.selectbox(
        "Gemini Vision Model:",
        options=["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash"],
        index=0,
        help="Primary model is Gemini 3.8 Flash. Includes automatic fallback if high-demand spikes occur.",
    )

    api_key_configured = bool(os.getenv("GEMINI_API_KEY"))
    if api_key_configured:
        st.success("API Status: Connected")
    else:
        st.error("API Status: GEMINI_API_KEY missing in .env")

    st.divider()
    st.caption("🔒 **Privacy Guarantee:** All cases are stored locally with de-identified IDs (CR-YYYY-NNN). No patient identifiers are transmitted.")


# ==============================================================================
# VIEW 1: READING ROOM (ANALYZE & COMPARE)
# ==============================================================================
if navigation == "🩺 Reading Room (Analyze & Compare)":
    st.title("🩻 Reading Room: Chest Radiograph Analysis")
    st.markdown(
        "Upload a current chest radiograph, optionally attach a prior study for interval comparison, "
        "and provide clinical intake context to generate a structured report."
    )

    col_left, col_right = st.columns([1, 1], gap="large")

    with col_left:
        st.subheader("1. Radiograph Acquisition")
        
        uploaded_file = st.file_uploader(
            "Current Chest Radiograph (PNG, JPG, JPEG, WEBP, BMP, TIFF)",
            type=["png", "jpg", "jpeg", "webp", "bmp", "tiff", "tif"],
            key="current_image_uploader",
            help="Select the current study for analysis.",
        )

        current_image = None
        if uploaded_file is not None:
            try:
                current_image = Image.open(uploaded_file)
            except Exception as e:
                st.error(f"Error loading image: {e}")

        # Prior Image Comparison Toggle
        has_prior = st.checkbox("Include Previous Radiograph for Interval Comparison", value=False)
        prior_file = None
        prior_image = None

        if has_prior:
            prior_file = st.file_uploader(
                "Prior Chest Radiograph (Comparison Baseline)",
                type=["png", "jpg", "jpeg", "webp", "bmp", "tiff", "tif"],
                key="prior_image_uploader",
                help="Select a previous radiograph to assess interval changes.",
            )
            if prior_file is not None:
                try:
                    prior_image = Image.open(prior_file)
                except Exception as e:
                    st.error(f"Error loading prior image: {e}")

        # Side-by-side or Single Image Display
        if current_image is not None and prior_image is not None:
            st.markdown("#### Side-by-Side Comparison")
            c_col1, c_col2 = st.columns(2)
            with c_col1:
                st.image(current_image, caption=f"Current: {uploaded_file.name}", use_container_width=True)
            with c_col2:
                st.image(prior_image, caption=f"Prior Baseline: {prior_file.name}", use_container_width=True)
        elif current_image is not None:
            st.image(current_image, caption=f"Current Study: {uploaded_file.name}", use_container_width=True)

        # Smart Clinical Intake
        st.markdown("---")
        st.subheader("2. Smart Clinical Intake (Optional)")
        st.caption("All clinical details are optional and used strictly as supporting context.")

        intake_c1, intake_c2 = st.columns(2)
        with intake_c1:
            patient_age = st.text_input("Patient Age", placeholder="e.g., 58 (or leave blank)")
            symptom_choice = st.selectbox(
                "Main Symptoms",
                options=[
                    "Not specified", "No symptoms", "Breathlessness", "Chest pain",
                    "Cough and fever", "Chest trauma", "Other"
                ],
                index=0,
            )
            custom_symptom = ""
            if symptom_choice == "Other":
                custom_symptom = st.text_input("Specify Other Symptom", placeholder="e.g., hemoptysis")

            projection_choice = st.selectbox(
                "X-ray Projection",
                options=["Not sure", "PA", "AP"],
                index=0,
            )

        with intake_c2:
            duration_choice = st.selectbox(
                "Duration of Symptoms",
                options=["Not provided", "Less than 24 hours", "1–3 days", "More than 3 days"],
                index=0,
            )
            history_choice = st.selectbox(
                "Relevant Medical History",
                options=["Unknown", "No known history", "Previous lung disease", "Previous chest trauma", "Other"],
                index=0,
            )
            custom_history = ""
            if history_choice == "Other":
                custom_history = st.text_input("Specify Other History", placeholder="e.g., COPD, asthma")

        additional_notes = st.text_area(
            "Additional Clinical Notes",
            placeholder="e.g., SpO2 93% on room air, elevated D-dimer, smoker (20 pack-years)...",
            height=70,
        )

        st.markdown("---")
        generate_clicked = st.button(
            "📋 Generate Radiology Report",
            type="primary",
            disabled=(uploaded_file is None),
            use_container_width=True,
        )

    with col_right:
        st.subheader("3. Structured Radiology Report & Verification")

        if "active_case_id" not in st.session_state:
            st.session_state.active_case_id = None
        if "active_report" not in st.session_state:
            st.session_state.active_report = None
        if "active_alert" not in st.session_state:
            st.session_state.active_alert = None
        if "active_teaching" not in st.session_state:
            st.session_state.active_teaching = None
        if "active_model" not in st.session_state:
            st.session_state.active_model = None

        if generate_clicked and current_image is not None:
            # Build structured context string
            intake_lines = []
            intake_lines.append(f"- **Patient Age:** {patient_age.strip() if patient_age else 'Not specified'}")
            final_sym = custom_symptom.strip() if (symptom_choice == "Other" and custom_symptom) else symptom_choice
            intake_lines.append(f"- **Main Symptoms:** {final_sym}")
            intake_lines.append(f"- **Duration:** {duration_choice}")
            final_hist = custom_history.strip() if (history_choice == "Other" and custom_history) else history_choice
            intake_lines.append(f"- **Relevant History:** {final_hist}")
            intake_lines.append(f"- **Indicated Projection:** {projection_choice}")
            if additional_notes and additional_notes.strip():
                intake_lines.append(f"- **Additional Notes:** {additional_notes.strip()}")
            clinical_summary = "\n".join(intake_lines)

            status_msg = f"Analyzing radiograph with {selected_model}..."
            if has_prior and prior_image is not None:
                status_msg = f"Performing dual-study interval comparison with {selected_model}..."

            with st.spinner(status_msg):
                try:
                    report_md, critical_alert, teaching_pts, model_used = analyze_image(
                        image=current_image,
                        prior_image=prior_image if has_prior else None,
                        clinical_history=clinical_summary,
                        model_name=selected_model,
                    )
                    # Save to local database
                    case_id = database.save_case(
                        report_markdown=report_md,
                        indication=clinical_summary,
                        projection=projection_choice,
                        has_prior=(has_prior and prior_image is not None),
                        critical_alert=critical_alert,
                        teaching_points=teaching_pts,
                        model_used=model_used,
                    )

                    st.session_state.active_case_id = case_id
                    st.session_state.active_report = report_md
                    st.session_state.active_alert = critical_alert
                    st.session_state.active_teaching = teaching_pts
                    st.session_state.active_model = model_used

                    st.success(f"Case `{case_id}` registered and report generated successfully!")
                except Exception as ex:
                    st.error(f"Analysis failed: {str(ex)}")

        # Display Report & Alerts
        if st.session_state.active_report:
            # Critical Alert Warning Banner
            if st.session_state.active_alert:
                st.error(
                    f"🚨 **CRITICAL RADIOLOGICAL FINDING ALERT**\n\n"
                    f"**Identified:** {st.session_state.active_alert}\n\n"
                    f"⚠️ **URGENT CLINICAL AND SENIOR RADIOLOGIST ASSESSMENT REQUIRED IMMEDIATELY.**",
                    icon="🚨",
                )

            # Metadata Bar
            c_meta1, c_meta2 = st.columns(2)
            with c_meta1:
                st.caption(f"📁 **Case ID:** `{st.session_state.active_case_id}`")
            with c_meta2:
                st.caption(f"🧠 **AI Engine:** `{st.session_state.active_model}`")

            # Report Viewer
            st.markdown(st.session_state.active_report)

            st.divider()

            # Downloads & Actions
            d_col1, d_col2 = st.columns(2)
            with d_col1:
                # PDF Generation
                exam_date = datetime.now().strftime("%Y-%m-%d %H:%M")
                pdf_bytes = pdf_generator.generate_radiology_pdf(
                    case_id=st.session_state.active_case_id or "CR-CURRENT",
                    examination_date=exam_date,
                    report_markdown=st.session_state.active_report,
                    critical_alert=st.session_state.active_alert,
                    model_used=st.session_state.active_model or "gemini-3.8-flash",
                )
                st.download_button(
                    label="📄 Download Professional Clinical PDF",
                    data=pdf_bytes,
                    file_name=f"{st.session_state.active_case_id or 'CaseReady_Report'}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )

            with d_col2:
                st.download_button(
                    label="📥 Download Markdown (.md)",
                    data=st.session_state.active_report,
                    file_name=f"{st.session_state.active_case_id or 'CaseReady_Report'}.md",
                    mime="text/markdown",
                    use_container_width=True,
                )

            # Quick Link to Student Mode
            with st.expander("🎓 View Medical Student Learning Breakdown for this Case"):
                st.markdown(st.session_state.active_teaching)
        else:
            st.info(
                "👈 Upload a chest radiograph and click **'Generate Radiology Report'** to review the findings.",
                icon="ℹ️",
            )


# ==============================================================================
# VIEW 2: WORKLIST & CASE ARCHIVE
# ==============================================================================
elif navigation == "📋 Worklist & Case Archive":
    st.title("📋 Radiology Department Worklist & Case Archive")
    st.markdown("Manage de-identified patient examinations, view reporting status, and inspect prior reports.")

    all_cases = database.get_all_cases()

    if not all_cases:
        st.info("No cases have been analyzed yet. Head over to the **Reading Room** to analyze your first study!")
    else:
        # Metrics summary
        total_cases = len(all_cases)
        flagged_count = sum(1 for c in all_cases if c["status"] == "Flagged Critical")
        reviewed_count = sum(1 for c in all_cases if c["status"] == "Reviewed")
        pending_count = sum(1 for c in all_cases if c["status"] == "Pending Review")

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Studies", total_cases)
        m2.metric("Pending Review", pending_count)
        m3.metric("Verified by Radiologist", reviewed_count)
        m4.metric("Flagged Critical", flagged_count)

        st.divider()

        # Filter option
        status_filter = st.selectbox("Filter Worklist by Status:", ["All", "Pending Review", "Flagged Critical", "Reviewed"])
        filtered_cases = all_cases if status_filter == "All" else [c for c in all_cases if c["status"] == status_filter]

        # Table Display
        table_rows = []
        for c in filtered_cases:
            table_rows.append({
                "Case ID": c["case_id"],
                "Date / Time": c["created_at"],
                "Modality": "CXR",
                "Projection": c["projection"] or "Unknown",
                "Prior Comparison": "Yes" if c["has_prior"] else "None",
                "Reporting Status": c["status"],
                "Critical Alert": "🚨 YES" if c["critical_alert"] else "None",
            })
        st.dataframe(pd.DataFrame(table_rows), use_container_width=True)

        st.divider()
        st.subheader("Inspect Selected Case Record")
        case_options = [c["case_id"] for c in filtered_cases]
        selected_id = st.selectbox("Select Case ID to Review:", options=case_options)

        if selected_id:
            chosen_case = database.get_case_by_id(selected_id)
            if chosen_case:
                col_c1, col_c2 = st.columns([2, 1])
                with col_c1:
                    if chosen_case["critical_alert"]:
                        st.error(f"🚨 **CRITICAL FINDING ALERT:** {chosen_case['critical_alert']}")
                    st.markdown(chosen_case["report_markdown"])
                with col_c2:
                    st.markdown("#### Case Controls")
                    st.write(f"**Date:** {chosen_case['created_at']}")
                    st.write(f"**Current Status:** `{chosen_case['status']}`")

                    new_status = st.selectbox(
                        "Update Radiologist Review Status:",
                        options=["Pending Review", "Reviewed", "Flagged Critical"],
                        index=["Pending Review", "Reviewed", "Flagged Critical"].index(chosen_case["status"]),
                    )
                    if st.button("Update Status"):
                        database.update_case_status(selected_id, new_status)
                        st.success(f"Status for {selected_id} updated to {new_status}!")
                        st.rerun()

                    st.markdown("---")
                    pdf_dl = pdf_generator.generate_radiology_pdf(
                        case_id=chosen_case["case_id"],
                        examination_date=chosen_case["created_at"],
                        report_markdown=chosen_case["report_markdown"],
                        critical_alert=chosen_case["critical_alert"],
                        model_used=chosen_case["model_used"] or "gemini-3.8-flash",
                    )
                    st.download_button(
                        label="📄 Export Case as PDF",
                        data=pdf_dl,
                        file_name=f"{chosen_case['case_id']}.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                    )


# ==============================================================================
# VIEW 3: CASE-BASED LEARNING LIBRARY (NEW DEDICATED SECTION)
# ==============================================================================
elif navigation == "📚 Case-Based Learning Library":
    st.title("📚 Case-Based Radiology Learning Library")
    st.markdown(
        "Interactive chest X-ray teaching cases categorized by pathology and difficulty. "
        "Test your diagnostic reasoning with interactive quizzes and explore verified reference findings."
    )

    # 1. Filters & Search Bar
    with st.container():
        f1, f2, f3 = st.columns([2, 2, 3])
        with f1:
            category_filter = st.selectbox(
                "Filter by Disease / Pathology:",
                options=[
                    "All",
                    "Normal chest X-ray",
                    "Pneumothorax",
                    "Pneumonia",
                    "Pleural effusion",
                    "Atelectasis",
                    "Cardiomegaly",
                    "Pulmonary oedema",
                    "Other radiological abnormalities",
                ],
                index=0,
            )
        with f2:
            difficulty_filter = st.selectbox(
                "Filter by Difficulty:",
                options=["All", "Beginner", "Intermediate", "Advanced"],
                index=0,
            )
        with f3:
            search_query = st.text_input("🔍 Search cases by keyword:", placeholder="e.g. pneumothorax, fever, bat-wing...")

    learning_cases = database.get_learning_cases(
        category=category_filter,
        difficulty=difficulty_filter,
        search_query=search_query,
    )

    st.divider()

    if not learning_cases:
        st.warning("No educational cases match the selected filters. Try broadening your criteria.")
    else:
        # Case Selector
        case_titles = [f"{c['case_id']}: {c['title']} ({c['difficulty']})" for c in learning_cases]
        selected_idx = st.selectbox("Select Case Study to Open:", options=range(len(learning_cases)), format_func=lambda i: case_titles[i])
        active_edu_case = learning_cases[selected_idx]

        # Case Header Bar
        diff_color = "green" if active_edu_case["difficulty"] == "Beginner" else ("orange" if active_edu_case["difficulty"] == "Intermediate" else "red")
        st.markdown(
            f"### {active_edu_case['title']} "
            f":{diff_color}[[{active_edu_case['difficulty']}]] "
            f"• Category: `{active_edu_case['category']}`"
        )

        col_img_quiz, col_findings = st.columns([1, 1], gap="large")

        with col_img_quiz:
            st.subheader("1. Teaching Radiograph")
            if os.path.exists(active_edu_case["image_path"]):
                try:
                    edu_img = Image.open(active_edu_case["image_path"])
                    st.image(edu_img, caption=f"{active_edu_case['case_id']} - Verified Teaching Film", use_container_width=True)
                except Exception as e:
                    st.error(f"Error loading case image: {e}")
            else:
                st.info("Teaching film illustration path registered.")

            st.markdown("---")
            st.subheader("2. 🎯 Interactive Clinical Quiz")
            st.markdown(f"**Question:** {active_edu_case['quiz_question']}")

            quiz_options = json.loads(active_edu_case["quiz_options"])
            quiz_key = f"quiz_{active_edu_case['case_id']}"
            selected_option_idx = st.radio(
                "Select your answer:",
                options=range(len(quiz_options)),
                format_func=lambda i: quiz_options[i],
                key=quiz_key,
            )

            submit_quiz = st.button("Submit Answer & Reveal Verified Rationale", type="primary", key=f"btn_{active_edu_case['case_id']}")

            if submit_quiz:
                correct_idx = active_edu_case["quiz_correct_index"]
                if selected_option_idx == correct_idx:
                    st.success("🎉 **Correct!** Outstanding radiological identification.")
                else:
                    st.error(f"❌ **Incorrect.** The verified correct answer is: **{quiz_options[correct_idx]}**")

                st.markdown("#### Detailed Answer Rationale & Distractor Analysis:")
                st.info(active_edu_case["quiz_explanation"])

        with col_findings:
            st.subheader("3. Verified Clinical Study File")
            
            with st.expander("👤 Clinical History & Presenting Symptoms", expanded=True):
                st.write(active_edu_case["clinical_history"])

            with st.expander("🔍 Verified Radiological Findings", expanded=True):
                st.write(active_edu_case["verified_findings"])

            with st.expander("🎯 Diagnostic Impression & Differential Diagnoses", expanded=True):
                st.markdown(f"**Impression:**\n{active_edu_case['diagnostic_impression']}")
                st.markdown(f"**Differential Diagnoses:**\n{active_edu_case['differential_diagnoses']}")

            with st.expander("💡 Pathophysiological Explanation (Why It Matters)", expanded=False):
                st.write(active_edu_case["explanation"])

            with st.expander("📌 Key Clinical & Exam Learning Points", expanded=False):
                st.write(active_edu_case["learning_points"])

    # 4. Educator Case Authoring Section
    st.divider()
    with st.expander("➕ Author New Verified Educational Case (Authorized Faculty)"):
        st.markdown("Authorized educators can add verified, de-identified chest X-ray cases to the permanent learning repository.")

        with st.form("new_edu_case_form"):
            c_f1, c_f2, c_f3 = st.columns([2, 1, 1])
            with c_f1:
                new_title = st.text_input("Case Title", placeholder="e.g., Left Upper Lobe Collapse with Golden S Sign")
            with c_f2:
                new_cat = st.selectbox(
                    "Pathology Category:",
                    options=[
                        "Normal chest X-ray", "Pneumothorax", "Pneumonia", "Pleural effusion",
                        "Atelectasis", "Cardiomegaly", "Pulmonary oedema", "Other radiological abnormalities"
                    ],
                )
            with c_f3:
                new_diff = st.selectbox("Difficulty Level:", options=["Beginner", "Intermediate", "Advanced"])

            new_img_file = st.file_uploader("Upload De-Identified Teaching Radiograph", type=["png", "jpg", "jpeg", "webp"])
            new_history = st.text_area("Clinical History & Presenting Symptoms", placeholder="Patient age, symptoms, onset...")
            new_findings = st.text_area("Verified Radiological Findings", placeholder="Systematic findings observed on film...")
            new_impression = st.text_area("Diagnostic Impression", placeholder="Final verified diagnosis...")
            new_explanation = st.text_area("Pathophysiological Explanation", placeholder="Explain why the finding occurs...")
            new_differentials = st.text_area("Differential Diagnoses", placeholder="1. Primary etiology\n2. Key differentials...")
            new_pearls = st.text_area("Clinical Learning Points", placeholder="High-yield pearls for exams/ward rounds...")

            st.markdown("##### Quiz Configuration")
            new_q = st.text_input("Quiz Question", placeholder="e.g. Which radiological sign indicates volume loss in this lobe?")
            opt1 = st.text_input("Option A", placeholder="Choice 1")
            opt2 = st.text_input("Option B", placeholder="Choice 2")
            opt3 = st.text_input("Option C", placeholder="Choice 3")
            opt4 = st.text_input("Option D", placeholder="Choice 4")
            correct_choice = st.selectbox("Correct Option Index:", options=["Option A (0)", "Option B (1)", "Option C (2)", "Option D (3)"])
            new_q_exp = st.text_area("Quiz Explanation & Distractor Analysis", placeholder="Explain why the answer is correct and why other choices are wrong...")

            save_edu_btn = st.form_submit_button("💾 Save Verified Educational Case", type="primary")

            if save_edu_btn:
                if not new_title or not new_history or not new_findings or not new_q or not opt1 or not opt2:
                    st.error("Please fill in all mandatory case and quiz fields.")
                else:
                    # Save image if provided
                    saved_img_path = os.path.join(os.path.dirname(__file__), "learning_library_images", f"custom_{datetime.now().strftime('%Y%m%d%H%M%S')}.png")
                    if new_img_file is not None:
                        with open(saved_img_path, "wb") as f:
                            f.write(new_img_file.getbuffer())
                    else:
                        saved_img_path = os.path.join(os.path.dirname(__file__), "learning_library_images", "edu_normal_cxr.png")

                    corr_idx_map = {"Option A (0)": 0, "Option B (1)": 1, "Option C (2)": 2, "Option D (3)": 3}
                    new_case_payload = {
                        "title": new_title.strip(),
                        "category": new_cat,
                        "difficulty": new_diff,
                        "image_path": saved_img_path,
                        "clinical_history": new_history.strip(),
                        "verified_findings": new_findings.strip(),
                        "diagnostic_impression": new_impression.strip(),
                        "explanation": new_explanation.strip(),
                        "differential_diagnoses": new_differentials.strip(),
                        "learning_points": new_pearls.strip(),
                        "quiz_question": new_q.strip(),
                        "quiz_options": [opt1.strip(), opt2.strip(), opt3.strip() if opt3 else "", opt4.strip() if opt4 else ""],
                        "quiz_correct_index": corr_idx_map[correct_choice],
                        "quiz_explanation": new_q_exp.strip(),
                    }
                    new_id = database.add_learning_case(new_case_payload)
                    st.success(f"Educational Case `{new_id}` saved successfully to the library!")
                    st.rerun()


# ==============================================================================
# VIEW 4: MEDICAL STUDENT LEARNING CENTER (CASE PEARLS)
# ==============================================================================
elif navigation == "🎓 Student Learning Center":
    st.title("🎓 Medical Student Radiology Learning Center")
    st.markdown(
        "Educational teaching files and pathophysiological breakdowns generated from clinical analyses "
        "to help medical students understand **why** findings occur and how to interpret chest X-rays systematically."
    )

    all_cases = database.get_all_cases()
    teaching_cases = [c for c in all_cases if c["teaching_points"]]

    if not teaching_cases:
        st.info(
            "No analyzed teaching files available yet. Analyze a radiograph in the **Reading Room** to generate an automated educational teaching file!"
        )
    else:
        st.subheader("Select Analyzed Teaching File")
        case_pick = st.selectbox(
            "Choose Case Study:",
            options=[c["case_id"] for c in teaching_cases],
            format_func=lambda x: f"{x} (Recorded: {next(c['created_at'] for c in teaching_cases if c['case_id'] == x)})",
        )

        selected_case = next(c for c in teaching_cases if c["case_id"] == case_pick)

        tab1, tab2 = st.tabs(["📚 Educational Breakdown & Anatomy", "📄 Formal Radiology Report"])

        with tab1:
            if selected_case["critical_alert"]:
                st.warning(f"⚠️ **High-Yield Emergency Concept:** {selected_case['critical_alert']}")
            st.markdown(selected_case["teaching_points"])

        with tab2:
            st.markdown(selected_case["report_markdown"])


# ==============================================================================
# VIEW 5: AI EVALUATION & PERFORMANCE DASHBOARD
# ==============================================================================
elif navigation == "📊 AI Evaluation & Performance":
    st.title("📊 AI Performance & Validation Dashboard")
    st.markdown(
        "Empirical diagnostic validation framework. Record ground-truth verified radiologist findings, "
        "audit true/false positives, and evaluate diagnostic agreement **without synthetic or fabricated metrics**."
    )

    metrics = database.get_evaluation_metrics()

    # Metric Cards
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Evaluated Cases", metrics["total_cases_evaluated"])
    c2.metric("Radiologist Agreement", f"{metrics['agreement_rate']}%" if metrics["total_cases_evaluated"] > 0 else "N/A")
    c3.metric("True Positives (TP)", metrics["total_true_positives"])
    c4.metric("False Positives (FP)", metrics["total_false_positives"])
    c5.metric("False Negatives (FN)", metrics["total_false_negatives"])

    st.caption("All statistics are calculated strictly from verified test records in the database. No metrics are simulated.")

    st.divider()

    # Two-Column Evaluation Workspace
    eval_col1, eval_col2 = st.columns([1, 1], gap="large")

    with eval_col1:
        st.subheader("1. Record Verified Reference Evaluation")
        all_cases = database.get_all_cases()

        if not all_cases:
            st.info("No cases exist in the database. First analyze an examination in the Reading Room.")
        else:
            eval_case_id = st.selectbox("Select Case ID to Benchmark:", options=[c["case_id"] for c in all_cases])
            target_case = next((c for c in all_cases if c["case_id"] == eval_case_id), None)

            if target_case:
                st.caption(f"Recorded Date: {target_case['created_at']}")
                with st.expander("Peek at AI Impression"):
                    st.markdown(target_case["report_markdown"][:500] + "...")

            ref_report = st.text_area(
                "Verified Radiologist Reference Diagnosis / Ground Truth",
                placeholder="e.g., Right middle lobe consolidation consistent with community-acquired pneumonia. No pneumothorax.",
                height=90,
            )

            agreed = st.radio("Did AI Primary Finding Agree with Ground Truth?", ["Yes", "No"], index=0)

            c_tp, c_fp, c_fn = st.columns(3)
            with c_tp:
                tp_count = st.number_input("True Positives (TP)", min_value=0, max_value=20, value=1, help="Correctly identified abnormalities")
            with c_fp:
                fp_count = st.number_input("False Positives (FP)", min_value=0, max_value=20, value=0, help="Hallucinated or non-existent findings reported")
            with c_fn:
                fn_count = st.number_input("False Negatives (FN)", min_value=0, max_value=20, value=0, help="Missed abnormalities present on radiograph")

            human_review = st.checkbox("Requires Human Radiologist Review / Correction?", value=True)
            eval_notes = st.text_input("Evaluator Notes (Optional)", placeholder="e.g., Subtle apical pleural line missed on AI pass")

            submit_eval = st.button("💾 Save Verified Benchmark Evaluation", type="primary", use_container_width=True)

            if submit_eval:
                if not ref_report.strip():
                    st.error("Please enter the verified reference diagnosis before saving.")
                else:
                    database.save_evaluation(
                        case_id=eval_case_id,
                        reference_report=ref_report.strip(),
                        findings_agreed=(agreed == "Yes"),
                        true_positives=int(tp_count),
                        false_positives=int(fp_count),
                        false_negatives=int(fn_count),
                        requires_human_review=human_review,
                        evaluator_notes=eval_notes.strip(),
                    )
                    st.success(f"Benchmark record for {eval_case_id} recorded successfully!")
                    st.rerun()

    with eval_col2:
        st.subheader("2. Verified Evaluation Records")
        eval_records = database.get_all_evaluations()

        if not eval_records:
            st.info("No benchmark evaluations recorded yet. Use the form on the left to benchmark evaluated cases.")
        else:
            eval_df_rows = []
            for r in eval_records:
                eval_df_rows.append({
                    "Case ID": r["case_id"],
                    "Evaluated At": r["evaluated_at"],
                    "Agreed": "✅ Yes" if r["findings_agreed"] else "❌ No",
                    "TP": r["true_positives"],
                    "FP": r["false_positives"],
                    "FN": r["false_negatives"],
                    "Human Review": "Required" if r["requires_human_review"] else "Not Required",
                    "Notes": r["evaluator_notes"] or "-",
                })
            st.dataframe(pd.DataFrame(eval_df_rows), use_container_width=True)
