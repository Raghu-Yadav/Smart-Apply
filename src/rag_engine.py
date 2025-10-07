import json
import os
import hashlib
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import numpy as np

from langchain.embeddings import HuggingFaceEmbeddings
from langchain.vectorstores import FAISS
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document
from langchain_groq import ChatGroq
from langchain.chains import ConversationalRetrievalChain
from langchain.memory import ConversationBufferMemory
from langchain.prompts import PromptTemplate
from dotenv import load_dotenv

load_dotenv()

@dataclass
class JobSearchResult:
    job_id: str
    title: str
    company: str
    location: str
    salary_range: str
    experience_required: str
    match_score: float
    description: str
    skills_required: List[str]

class RAGEngine:
    def __init__(self, jobs_file_path: str = "data/jobs.json"):
        self.jobs_file_path = jobs_file_path
        self.jobs_data = self._load_jobs()
        self.embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )
        self.vector_store = None
        self.conversation_memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True,
            output_key="answer"
        )
        self.llm = self._initialize_llm()
        self._initialize_vector_store()
        
    def _load_jobs(self) -> List[Dict]:
        with open(self.jobs_file_path, 'r') as f:
            data = json.load(f)
        return data['jobs']
    
    def _initialize_llm(self):
        from langchain_groq import ChatGroq
        return ChatGroq(
            temperature=0.7,
            model="llama-3.3-70b-versatile",
            groq_api_key=os.getenv("GROQ_API_KEY")
        )
    
    def _create_job_documents(self) -> List[Document]:
        documents = []
        
        for job in self.jobs_data:
            content = f"""
            Job ID: {job['job_id']}
            Title: {job['title']}
            Company: {job['company']}
            Location: {job['location']}
            Experience Required: {job['experience_required']}
            Salary Range: {job['salary_range']}
            Skills: {', '.join(job['skills_required'])}
            Description: {job['description']}
            Responsibilities: {'. '.join(job['responsibilities'])}
            Qualifications: {'. '.join(job['qualifications'])}
            """
            
            doc = Document(
                page_content=content,
                metadata={
                    "job_id": job['job_id'],
                    "title": job['title'],
                    "company": job['company'],
                    "location": job['location'],
                    "salary_range": job['salary_range'],
                    "experience_required": job['experience_required'],
                    "skills": json.dumps(job['skills_required']),
                    "description": job['description'] 
                }
            )
            documents.append(doc)
            
        return documents
    
    def _get_jobs_hash(self) -> str:
        with open(self.jobs_file_path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()
    
    def _check_index_validity(self) -> bool:
        index_path = "faiss_index"
        hash_file = os.path.join(index_path, ".jobs_hash")
        
        if not os.path.exists(index_path) or not os.path.exists(hash_file):
            return False
        
        try:
            with open(hash_file, 'r') as f:
                saved_hash = f.read().strip()
            current_hash = self._get_jobs_hash()
            return saved_hash == current_hash
        except Exception:
            return False
    
    def _save_jobs_hash(self):
        index_path = "faiss_index"
        hash_file = os.path.join(index_path, ".jobs_hash")
        
        os.makedirs(index_path, exist_ok=True)
        with open(hash_file, 'w') as f:
            f.write(self._get_jobs_hash())
    
    def _initialize_vector_store(self):
        index_path = "faiss_index"
        
        # Check if index exists and is valid (jobs.json hasn't changed)
        if self._check_index_validity():
            try:
                # Load existing index
                self.vector_store = FAISS.load_local(
                    index_path, 
                    self.embeddings,
                    allow_dangerous_deserialization=True
                )
                print("✓ Loaded existing FAISS index (jobs.json unchanged)")
                return
            except Exception as e:
                print(f"Error loading index: {e}. Creating new index...")
        else:
            if os.path.exists(index_path):
                print("⚠ Jobs data changed, recreating index...")
            else:
                print("Creating new FAISS index for first time...")
        
        # Create new index
        documents = self._create_job_documents()
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50
        )
        split_docs = text_splitter.split_documents(documents)
        self.vector_store = FAISS.from_documents(split_docs, self.embeddings)
        
        # Save index and hash for future use
        self.vector_store.save_local(index_path)
        self._save_jobs_hash()
        print("✓ FAISS index created and saved successfully")
    
    def search_jobs(
        self, 
        query: str, 
        k: int = 5,
        filters: Optional[Dict] = None
    ) -> List[JobSearchResult]:
        
        results = self.vector_store.similarity_search_with_score(query, k=k)
        
        job_results = []
        seen_jobs = set()
        
        for doc, score in results:
            job_id = doc.metadata.get('job_id')
            
            if job_id and job_id not in seen_jobs:
                seen_jobs.add(job_id)
                
                result = JobSearchResult(
                    job_id=job_id,
                    title=doc.metadata.get('title', ''),
                    company=doc.metadata.get('company', ''),
                    location=doc.metadata.get('location', ''),
                    salary_range=doc.metadata.get('salary_range', ''),
                    experience_required=doc.metadata.get('experience_required', ''),
                    match_score=float(1 / (1 + score)),
                    description=doc.metadata.get('description', ''),
                    skills_required=json.loads(doc.metadata.get('skills', '[]'))
                )
                
                if filters:
                    if 'location' in filters and filters['location'].lower() not in result.location.lower():
                        continue
                    if 'min_salary' in filters:
                        try:
                            salary_min = int(result.salary_range.split('-')[0].replace(' LPA', ''))
                            if salary_min < filters['min_salary']:
                                continue
                        except:
                            pass
                    if 'experience' in filters:
                        exp_filter = filters['experience']
                        job_exp = result.experience_required.lower()
                    
                    # Simple keyword matching - you can make this smarter
                        if exp_filter == "0-2 years" and "0-2" not in job_exp and "0-1" not in job_exp and "1-2" not in job_exp:
                            continue
                        elif exp_filter == "2-4 years" and "2-4" not in job_exp and "2-3" not in job_exp and "3-4" not in job_exp:
                            continue
                
                job_results.append(result)
        
        return job_results[:k]
    
    def get_job_by_id(self, job_id: str) -> Optional[Dict]:
        for job in self.jobs_data:
            if job['job_id'] == job_id:
                return job
        return None
    
    def generate_conversational_response(self, user_input: str) -> Dict[str, Any]:
        prompt_template = """You are JobMatch AI, a helpful assistant for job seekers. 
        Use the following context about available jobs to answer questions.
        If asked about jobs, provide relevant matches with job IDs.
        Be conversational and helpful.
        
        Context: {context}
        Chat History: {chat_history}
        Question: {question}
        
        Response:"""
        
        prompt = PromptTemplate(
            template=prompt_template,
            input_variables=["context", "chat_history", "question"]
        )
        
        qa_chain = ConversationalRetrievalChain.from_llm(
            llm=self.llm,
            retriever=self.vector_store.as_retriever(search_kwargs={"k": 3}),
            memory=self.conversation_memory,
            combine_docs_chain_kwargs={"prompt": prompt},
            return_source_documents=True
        )
        
        result = qa_chain({"question": user_input})
        
        job_results = self.search_jobs(user_input, k=3)
        
        return {
            "response": result['answer'],
            "source_jobs": job_results,
            "chat_history": self.conversation_memory.chat_memory.messages
        }
    
    def process_application(
        self, 
        job_id: str, 
        candidate_info: Dict,
        screening_answers: List[Dict]
    ) -> Dict[str, Any]:
        
        job = self.get_job_by_id(job_id)
        if not job:
            return {"success": False, "message": "Job not found"}
        
        application = {
            "job_id": job_id,
            "job_title": job['title'],
            "company": job['company'],
            "candidate_info": candidate_info,
            "screening_answers": screening_answers,
            "status": "submitted"
        }
        
        return {
            "success": True,
            "message": "Application submitted successfully",
            "application": application
        }
    
    def get_screening_questions(self, job_id: str) -> List[Dict]:
        job = self.get_job_by_id(job_id)
        if job:
            return job.get('screening_questions', [])
        return []
    
    def reset_conversation(self):
        self.conversation_memory.clear()

class JobApplicationSession:
    def __init__(self, rag_engine: RAGEngine):
        self.rag_engine = rag_engine
        self.state = "searching"
        self.selected_job = None
        self.candidate_info = {}
        self.screening_answers = []
        self.current_question_index = 0
    
    def process_message(self, message: str) -> Dict[str, Any]:
        
        if self.state == "searching":
            response = self.rag_engine.generate_conversational_response(message)
            
            if any(keyword in message.lower() for keyword in ['apply', 'interested', 'select']):
                job_ids = self._extract_job_id(message)
                if job_ids:
                    self.selected_job = job_ids[0]
                    self.state = "applying"
                    questions = self.rag_engine.get_screening_questions(self.selected_job)
                    return {
                        "state": "applying",
                        "message": "Great! Please upload your resume to proceed with the application.",
                        "job_id": self.selected_job,
                        "needs_resume": True
                    }
            
            return {
                "state": "searching",
                "response": response['response'],
                "jobs": response['source_jobs']
            }
        
        elif self.state == "applying":
            return self._handle_application_state(message)
        
        elif self.state == "answering":
            return self._handle_screening_questions(message)
    
    def _extract_job_id(self, message: str) -> List[str]:
        import re
        pattern = r'JOB\d{3}'
        return re.findall(pattern, message.upper())
    
    def _handle_application_state(self, message: str) -> Dict[str, Any]:
        self.state = "answering"
        questions = self.rag_engine.get_screening_questions(self.selected_job)
        
        if questions:
            return {
                "state": "answering",
                "message": f"Now I'll ask you {len(questions)} screening questions.",
                "question": questions[0],
                "question_index": 0,
                "total_questions": len(questions)
            }
        else:
            return self._submit_application()
    
    def _handle_screening_questions(self, answer: str) -> Dict[str, Any]:
        questions = self.rag_engine.get_screening_questions(self.selected_job)
        
        self.screening_answers.append({
            "question": questions[self.current_question_index]['question'],
            "answer": answer
        })
        
        self.current_question_index += 1
        
        if self.current_question_index < len(questions):
            return {
                "state": "answering",
                "question": questions[self.current_question_index],
                "question_index": self.current_question_index,
                "total_questions": len(questions)
            }
        else:
            return self._submit_application()
    
    def _submit_application(self) -> Dict[str, Any]:
        result = self.rag_engine.process_application(
            self.selected_job,
            self.candidate_info,
            self.screening_answers
        )
        
        self.reset()
        
        return {
            "state": "completed",
            "message": "Your application has been submitted successfully!",
            "result": result
        }
    
    def reset(self):
        self.state = "searching"
        self.selected_job = None
        self.candidate_info = {}
        self.screening_answers = []
        self.current_question_index = 0
        self.rag_engine.reset_conversation()