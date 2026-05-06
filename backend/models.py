from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(String)  # student, teacher, admin
    
    # VARK Vector
    vark_v = Column(Float, default=0.25)
    vark_a = Column(Float, default=0.25)
    vark_r = Column(Float, default=0.25)
    vark_k = Column(Float, default=0.25)
    
    # Expertise
    pas = Column(Float, default=0.0)  # Previous Academic Score
    
    mastery_logs = relationship("MasteryLog", back_populates="user")

class WeightedSettings(Base):
    __tablename__ = "weighted_settings"
    id = Column(Integer, primary_key=True, index=True)
    w_prev = Column(Float, default=0.5)
    w_diag = Column(Float, default=0.5)

class CurriculumObject(Base):
    __tablename__ = "curriculum_objects"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    code = Column(String, unique=True, index=True)
    level = Column(String)
    description = Column(String)
    ground_truth_path = Column(String)
    excel_path = Column(String)  # Path to the source excel file
    excel_data_json = Column(JSON, default=[]) # Stored parsed table data
    quiz_questions = Column(JSON, default=[])  # Store quiz questions
    
    # Multi-modal content slots (JSON or Paths)
    modality_v = Column(JSON)  # Visual content data
    modality_a = Column(JSON)  # Auditory content data
    modality_r = Column(JSON)  # Reading content data
    modality_k = Column(JSON)  # Kinesthetic content data
    
    mastery_logs = relationship("MasteryLog", back_populates="curriculum")

class MasteryLog(Base):
    __tablename__ = "mastery_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    curriculum_id = Column(Integer, ForeignKey("curriculum_objects.id"))
    topic_idx = Column(Integer, nullable=True)
    score = Column(Float)
    modality_used = Column(String)  # V, A, R, or K
    feedback = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    
    user = relationship("User", back_populates="mastery_logs")
    curriculum = relationship("CurriculumObject", back_populates="mastery_logs")
