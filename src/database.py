import os
from datetime import datetime
from typing import List, Dict, Optional, Any
import json
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey, LargeBinary
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, Session
from dotenv import load_dotenv

load_dotenv()

Base = declarative_base()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///applications.db")

class Application(Base):
    __tablename__ = "applications"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(50), nullable=False)
    job_title = Column(String(200), nullable=False)
    company = Column(String(200), nullable=False)
    candidate_name = Column(String(200), nullable=False)
    candidate_email = Column(String(200), nullable=False)
    candidate_phone = Column(String(20))
    candidate_location = Column(String(200))
    status = Column(String(50), default="submitted")
    submitted_at = Column(DateTime, default=datetime.utcnow)
    
    screening_responses = relationship("ScreeningResponse", back_populates="application", cascade="all, delete-orphan")
    resume = relationship("Resume", back_populates="application", uselist=False, cascade="all, delete-orphan")

class ScreeningResponse(Base):
    __tablename__ = "screening_responses"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=False)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    question_type = Column(String(50))
    
    application = relationship("Application", back_populates="screening_responses")

class Resume(Base):
    __tablename__ = "resumes"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=False)
    file_name = Column(String(255), nullable=False)
    file_content = Column(LargeBinary, nullable=False)
    file_type = Column(String(50))
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    
    application = relationship("Application", back_populates="resume")

class DatabaseManager:
    def __init__(self):
        self.engine = create_engine(DATABASE_URL, echo=False)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
    
    def get_session(self) -> Session:
        return self.SessionLocal()
    
    def create_application(
        self,
        job_id: str,
        job_title: str,
        company: str,
        candidate_info: Dict[str, Any],
        screening_answers: List[Dict[str, str]] = None,
        resume_data: Dict[str, Any] = None
    ) -> int:
        
        session = self.get_session()
        try:
            application = Application(
                job_id=job_id,
                job_title=job_title,
                company=company,
                candidate_name=candidate_info.get("name", ""),
                candidate_email=candidate_info.get("email", ""),
                candidate_phone=candidate_info.get("phone", ""),
                candidate_location=candidate_info.get("location", ""),
                status="submitted"
            )
            session.add(application)
            session.flush()
            
            if screening_answers:
                for answer_data in screening_answers:
                    response = ScreeningResponse(
                        application_id=application.id,
                        question=answer_data.get("question", ""),
                        answer=answer_data.get("answer", ""),
                        question_type=answer_data.get("type", "text")
                    )
                    session.add(response)
            
            if resume_data:
                resume = Resume(
                    application_id=application.id,
                    file_name=resume_data.get("file_name", "resume.pdf"),
                    file_content=resume_data.get("file_content", b""),
                    file_type=resume_data.get("file_type", "application/pdf")
                )
                session.add(resume)
            
            session.commit()
            return application.id
            
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()
    
    def get_application(self, application_id: int) -> Optional[Dict[str, Any]]:
        session = self.get_session()
        try:
            application = session.query(Application).filter_by(id=application_id).first()
            
            if not application:
                return None
            
            result = {
                "id": application.id,
                "job_id": application.job_id,
                "job_title": application.job_title,
                "company": application.company,
                "candidate": {
                    "name": application.candidate_name,
                    "email": application.candidate_email,
                    "phone": application.candidate_phone,
                    "location": application.candidate_location
                },
                "status": application.status,
                "submitted_at": application.submitted_at.isoformat(),
                "screening_responses": [
                    {
                        "question": response.question,
                        "answer": response.answer,
                        "type": response.question_type
                    }
                    for response in application.screening_responses
                ],
                "has_resume": application.resume is not None
            }
            
            return result
            
        finally:
            session.close()
    
    def get_all_applications(
        self, 
        status: Optional[str] = None,
        job_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        
        session = self.get_session()
        try:
            query = session.query(Application)
            
            if status:
                query = query.filter_by(status=status)
            if job_id:
                query = query.filter_by(job_id=job_id)
            
            applications = query.order_by(Application.submitted_at.desc()).limit(limit).all()
            
            results = []
            for app in applications:
                results.append({
                    "id": app.id,
                    "job_id": app.job_id,
                    "job_title": app.job_title,
                    "company": app.company,
                    "candidate_name": app.candidate_name,
                    "candidate_email": app.candidate_email,
                    "status": app.status,
                    "submitted_at": app.submitted_at.isoformat()
                })
            
            return results
            
        finally:
            session.close()
    
    def update_application_status(self, application_id: int, new_status: str) -> bool:
        session = self.get_session()
        try:
            application = session.query(Application).filter_by(id=application_id).first()
            
            if not application:
                return False
            
            application.status = new_status
            session.commit()
            return True
            
        except Exception:
            session.rollback()
            return False
        finally:
            session.close()
    
    def save_resume(
        self, 
        application_id: int, 
        file_name: str, 
        file_content: bytes, 
        file_type: str = "application/pdf"
    ) -> bool:
        
        session = self.get_session()
        try:
            existing_resume = session.query(Resume).filter_by(application_id=application_id).first()
            
            if existing_resume:
                existing_resume.file_name = file_name
                existing_resume.file_content = file_content
                existing_resume.file_type = file_type
                existing_resume.uploaded_at = datetime.utcnow()
            else:
                resume = Resume(
                    application_id=application_id,
                    file_name=file_name,
                    file_content=file_content,
                    file_type=file_type
                )
                session.add(resume)
            
            session.commit()
            return True
            
        except Exception:
            session.rollback()
            return False
        finally:
            session.close()
    
    def get_resume(self, application_id: int) -> Optional[Dict[str, Any]]:
        session = self.get_session()
        try:
            resume = session.query(Resume).filter_by(application_id=application_id).first()
            
            if not resume:
                return None
            
            return {
                "file_name": resume.file_name,
                "file_content": resume.file_content,
                "file_type": resume.file_type,
                "uploaded_at": resume.uploaded_at.isoformat()
            }
            
        finally:
            session.close()
    
    def get_application_stats(self) -> Dict[str, Any]:
        session = self.get_session()
        try:
            total = session.query(Application).count()
            submitted = session.query(Application).filter_by(status="submitted").count()
            reviewed = session.query(Application).filter_by(status="reviewed").count()
            accepted = session.query(Application).filter_by(status="accepted").count()
            rejected = session.query(Application).filter_by(status="rejected").count()
            
            return {
                "total_applications": total,
                "submitted": submitted,
                "reviewed": reviewed,
                "accepted": accepted,
                "rejected": rejected
            }
            
        finally:
            session.close()
    
    def search_applications(self, search_term: str) -> List[Dict[str, Any]]:
        session = self.get_session()
        try:
            applications = session.query(Application).filter(
                (Application.candidate_name.contains(search_term)) |
                (Application.candidate_email.contains(search_term)) |
                (Application.job_title.contains(search_term)) |
                (Application.company.contains(search_term))
            ).limit(50).all()
            
            results = []
            for app in applications:
                results.append({
                    "id": app.id,
                    "job_title": app.job_title,
                    "company": app.company,
                    "candidate_name": app.candidate_name,
                    "candidate_email": app.candidate_email,
                    "status": app.status,
                    "submitted_at": app.submitted_at.isoformat()
                })
            
            return results
            
        finally:
            session.close()

db_manager = DatabaseManager()