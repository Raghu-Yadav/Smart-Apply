import streamlit as st
import json
from typing import Dict, List, Any
import io
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.rag_engine import RAGEngine, JobApplicationSession
from src.database import db_manager

st.set_page_config(
    page_title="SmartHire - AI Job Application Assistant",
    page_icon="💼",
    layout="wide"
)

@st.cache_resource
def initialize_rag_engine():
    return RAGEngine("data/jobs.json")

def initialize_session_state():
    if 'rag_engine' not in st.session_state:
        st.session_state.rag_engine = initialize_rag_engine()
    
    if 'app_session' not in st.session_state:
        st.session_state.app_session = JobApplicationSession(st.session_state.rag_engine)
    
    if 'messages' not in st.session_state:
        st.session_state.messages = []
    
    if 'selected_job' not in st.session_state:
        st.session_state.selected_job = None
    
    if 'candidate_info' not in st.session_state:
        st.session_state.candidate_info = {}
    
    if 'screening_answers' not in st.session_state:
        st.session_state.screening_answers = []
    
    if 'current_question_index' not in st.session_state:
        st.session_state.current_question_index = 0
    
    if 'application_state' not in st.session_state:
        st.session_state.application_state = 'searching'
    
    if 'resume_uploaded' not in st.session_state:
        st.session_state.resume_uploaded = False
    
    if 'search_results' not in st.session_state:
        st.session_state.search_results = []
    
    if 'resume_data' not in st.session_state:
        st.session_state.resume_data = {}

def display_job_card(job):
    with st.container():
        col1, col2, col3 = st.columns([3, 2, 1])
        
        with col1:
            st.markdown(f"**{job.title}**")
            st.markdown(f"*{job.company}* | 📍 {job.location}")
            st.markdown(f"👨‍💻 {job.experience_required}")
        
        with col2:
            st.markdown(f"💰 {job.salary_range}")
            if hasattr(job, 'match_score'):
                score_percentage = int(job.match_score * 100)
                st.progress(score_percentage / 100)
                st.caption(f"Match: {score_percentage}%")
        
        with col3:
            if st.button(f"Apply", key=f"apply_{job.job_id}"):
                st.session_state.selected_job = job.job_id
                st.session_state.application_state = 'applying'
                st.session_state.search_results = []  # Clear search results
                st.rerun()
        
        with st.expander(f"View Details - {job.job_id}"):
            st.markdown("**Required Skills:**")
            st.write(", ".join(job.skills_required))
            st.markdown("**Description:**")
            st.write(job.description[:500] + "..." if len(job.description) > 500 else job.description)

def handle_job_search():
    st.title("🔍 Find Your Dream Job")
    
    st.markdown("""
<style>
    div[data-testid="column"] {
        align-items: center;
        display: flex;
    }
</style>
""", unsafe_allow_html=True)

    search_col1, search_col2 = st.columns([3, 1])

    with search_col1:
        search_query = st.text_input(
            "What kind of job are you looking for?",
            placeholder="e.g., ML engineer in Bangalore, Data scientist role, Remote Python jobs..."
        )

    with search_col2:
        search_button = st.button("Search Jobs", type="primary", use_container_width=True)
    
    col1, col2, col3 = st.columns(3)
    with col1:
        location_filter = st.selectbox(
            "Location",
            ["All Locations", "Bangalore", "Mumbai", "Delhi NCR", "Hyderabad", "Chennai", "Pune", "Remote"]
        )
    with col2:
        min_salary = st.slider("Minimum Salary (LPA)", 0, 50, 0)
    with col3:
        experience_filter = st.selectbox(
            "Experience Level",
            ["All Levels", "0-2 years", "2-4 years", "3-5 years", "4-7 years", "5+ years"]
        )
    
    if search_button and search_query:
        with st.spinner("Searching for matching jobs..."):
            filters = {}
            if location_filter != "All Locations":
                filters['location'] = location_filter
            if min_salary > 0:
                filters['min_salary'] = min_salary
            if experience_filter != "All Levels":
                filters['experience'] = experience_filter
            
            st.session_state.search_results = st.session_state.rag_engine.search_jobs(
                search_query,
                k=10,
                filters=filters
            )
    
    # Display search results if they exist
    if st.session_state.search_results:
        st.success(f"Found {len(st.session_state.search_results)} matching jobs!")
        st.markdown("---")
        
        for job in st.session_state.search_results:
            display_job_card(job)
            st.markdown("---")
    
    elif search_button and search_query:
        st.info("No jobs found matching your criteria. Try adjusting your search terms.")
    
    elif not search_query:
        st.info("💡 **Quick Search Examples:**")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🤖 Show me ML/AI roles"):
                st.session_state.search_results = st.session_state.rag_engine.search_jobs("machine learning AI", k=5)
                st.rerun()
        
        with col2:
            if st.button("🏠 Remote positions"):
                st.session_state.search_results = st.session_state.rag_engine.search_jobs("remote work from home", k=5)
                st.rerun()

def handle_application():
    job = st.session_state.rag_engine.get_job_by_id(st.session_state.selected_job)
    
    if not job:
        st.error("Job not found!")
        return
    
    st.title(f"📝 Apply for {job['title']}")
    st.info(f"**Company:** {job['company']} | **Location:** {job['location']} | **Salary:** {job['salary_range']}")
    
    with st.form("application_form"):
        st.markdown("### Your Information")
        
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Full Name*", placeholder="John Doe")
            email = st.text_input("Email*", placeholder="john@example.com")
        
        with col2:
            phone = st.text_input("Phone Number*", placeholder="+91 9876543210")
            location = st.text_input("Current Location", placeholder="Bangalore, India")
        
        st.markdown("### Resume Upload")
        uploaded_file = st.file_uploader(
            "Upload your resume (PDF/DOCX)*",
            type=['pdf', 'docx'],
            help="Max file size: 5MB"
        )
        
        submitted = st.form_submit_button("Proceed to Screening Questions", type="primary", use_container_width=True)
        
        if submitted:
            if not all([name, email, phone, uploaded_file]):
                st.error("Please fill all required fields and upload your resume.")
            else:
                st.session_state.candidate_info = {
                    "name": name,
                    "email": email,
                    "phone": phone,
                    "location": location
                }
                
                if uploaded_file:
                    st.session_state.resume_data = {
                        "file_name": uploaded_file.name,
                        "file_content": uploaded_file.read(),
                        "file_type": uploaded_file.type
                    }
                    st.session_state.resume_uploaded = True
                
                st.session_state.application_state = 'screening'
                st.rerun()

def handle_screening_questions():
    job = st.session_state.rag_engine.get_job_by_id(st.session_state.selected_job)
    
    if not job:
        st.error("Job not found!")
        return
    
    questions = job.get('screening_questions', [])
    
    if not questions:
        submit_application()
        return
    
    st.title("📋 Screening Questions")
    st.info(f"Please answer {len(questions)} questions for the {job['title']} position")
    
    progress = (st.session_state.current_question_index / len(questions))
    st.progress(progress)
    st.caption(f"Question {st.session_state.current_question_index + 1} of {len(questions)}")
    
    if st.session_state.current_question_index < len(questions):
        current_q = questions[st.session_state.current_question_index]
        
        st.markdown(f"### {current_q['question']}")
        
        answer = None
        
        if current_q['type'] == 'text':
            answer = st.text_area(
                "Your answer:",
                height=150,
                placeholder="Type your detailed answer here..."
            )
        
        elif current_q['type'] == 'yes_no':
            answer = st.radio(
                "Select your answer:",
                ["Yes", "No"]
            )
        
        elif current_q['type'] == 'multiple_choice':
            answer = st.radio(
                "Select your answer:",
                current_q.get('options', [])
            )
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.session_state.current_question_index > 0:
                if st.button("← Previous", use_container_width=True):
                    st.session_state.current_question_index -= 1
                    st.rerun()
        
        with col2:
            if st.session_state.current_question_index < len(questions) - 1:
                if st.button("Next →", type="primary", use_container_width=True):
                    if answer:
                        st.session_state.screening_answers.append({
                            "question": current_q['question'],
                            "answer": answer,
                            "type": current_q['type']
                        })
                        st.session_state.current_question_index += 1
                        st.rerun()
                    else:
                        st.error("Please provide an answer before proceeding.")
            else:
                if st.button("Submit Application", type="primary", use_container_width=True):
                    if answer:
                        st.session_state.screening_answers.append({
                            "question": current_q['question'],
                            "answer": answer,
                            "type": current_q['type']
                        })
                        submit_application()
                    else:
                        st.error("Please provide an answer before submitting.")

def submit_application():
    job = st.session_state.rag_engine.get_job_by_id(st.session_state.selected_job)
    
    try:
        application_id = db_manager.create_application(
            job_id=st.session_state.selected_job,
            job_title=job['title'],
            company=job['company'],
            candidate_info=st.session_state.candidate_info,
            screening_answers=st.session_state.screening_answers,
            resume_data=st.session_state.resume_data if st.session_state.resume_uploaded else None
        )
        
        st.session_state.application_state = 'completed'
        st.session_state.application_id = application_id
        st.rerun()
        
    except Exception as e:
        st.error(f"Error submitting application: {str(e)}")

def handle_completion():
    st.balloons()
    st.success("🎉 **Application Submitted Successfully!**")
    
    st.markdown(f"""
    ### Application Details
    - **Application ID:** #{st.session_state.application_id}
    - **Candidate:** {st.session_state.candidate_info.get('name')}
    - **Email:** {st.session_state.candidate_info.get('email')}
    - **Status:** Submitted
    
    You will receive a confirmation email shortly. The hiring team will review your application and contact you within 5-7 business days.
    """)
    
    if st.button("Search for More Jobs", type="primary"):
        reset_application_state()
        st.rerun()

def reset_application_state():
    st.session_state.selected_job = None
    st.session_state.candidate_info = {}
    st.session_state.screening_answers = []
    st.session_state.current_question_index = 0
    st.session_state.application_state = 'searching'
    st.session_state.resume_uploaded = False
    st.session_state.search_results = []
    st.session_state.resume_data = {}
    st.session_state.app_session.reset()

def admin_dashboard():
    st.title("📊 Admin Dashboard")
    
    stats = db_manager.get_application_stats()
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Applications", stats['total_applications'])
    with col2:
        st.metric("Submitted", stats['submitted'])
    with col3:
        st.metric("Reviewed", stats['reviewed'])
    with col4:
        st.metric("Accepted", stats['accepted'])
    
    st.markdown("---")
    
    st.subheader("Recent Applications")
    applications = db_manager.get_all_applications(limit=10)
    
    if applications:
        for app in applications:
            with st.container():
                col1, col2, col3, col4 = st.columns([2, 2, 1, 1])
                with col1:
                    st.text(f"**{app['candidate_name']}**")
                    st.caption(app['candidate_email'])
                with col2:
                    st.text(app['job_title'])
                    st.caption(app['company'])
                with col3:
                    st.text(app['status'].upper())
                with col4:
                    if st.button("View", key=f"view_{app['id']}"):
                        st.write(db_manager.get_application(app['id']))
                st.markdown("---")
    else:
        st.info("No applications yet.")

def main():
    initialize_session_state()
    
    st.sidebar.title("🚀 SmartHire")
    st.sidebar.caption("AI-Powered Job Application Assistant")
    
    page = st.sidebar.radio(
        "Navigation",
        ["Job Search", "Admin Dashboard"],
        index=0
    )
    
    if page == "Admin Dashboard":
        admin_dashboard()
    else:
        if st.session_state.application_state == 'searching':
            handle_job_search()
        elif st.session_state.application_state == 'applying':
            handle_application()
        elif st.session_state.application_state == 'screening':
            handle_screening_questions()
        elif st.session_state.application_state == 'completed':
            handle_completion()
    
    st.sidebar.markdown("---")
    st.sidebar.caption("Built with ❤️ using Streamlit & LangChain")

if __name__ == "__main__":
    main()