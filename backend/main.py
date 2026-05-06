from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, status
from fastapi.middleware.cors import CORSMiddleware
from datetime import timedelta
from sqlalchemy.orm import Session
import models
import logic
import ai_service
import auth
from database import SessionLocal, engine
from pydantic import BaseModel
from typing import List, Optional
from fastapi.security import OAuth2PasswordRequestForm
import pandas as pd
import io

from fastapi.staticfiles import StaticFiles
import shutil
import os
import uuid

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Aegis Mastery LMS API")

def get_allowed_origins() -> list[str]:
    origins = os.getenv("CORS_ORIGINS")
    if origins:
        return [origin.strip() for origin in origins.split(",") if origin.strip()]
    return ["*"]


# Add CORS middleware FIRST
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount uploads directory
if not os.path.exists("uploads"):
    os.makedirs("uploads")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_user_access(current_user: models.User, user_id: int):
    if current_user.id != user_id and current_user.role not in ["lecturer", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this user's data"
        )


def upload_path(prefix: str, file_name: str) -> str:
    file_ext = os.path.splitext(file_name or "")[1]
    safe_ext = file_ext if len(file_ext) <= 16 else ""
    return f"uploads/{prefix}_{uuid.uuid4().hex}{safe_ext}"

# Pydantic models for request/response
class SettingsUpdate(BaseModel):
    w_prev: float
    w_diag: float

class DiagnosticResult(BaseModel):
    user_id: int
    score: float

class MasterySubmission(BaseModel):
    user_id: int
    curriculum_id: int
    score: float
    modality: str
    topic_idx: Optional[int] = None
    feedback: Optional[str] = None

class UserCreate(BaseModel):
    email: str
    password: str
    role: str # student, lecturer, admin
    pas: Optional[float] = 0.0
    v: Optional[float] = 0.25
    a: Optional[float] = 0.25
    r: Optional[float] = 0.25
    k: Optional[float] = 0.25

class TelemetryUpdate(BaseModel):
    modality: str
    engagement_time: float

class CurriculumGenerateRequest(BaseModel):
    title: str
    description: str
    text_content: str
    code: Optional[str] = None
    level: Optional[str] = None

class Token(BaseModel):
    access_token: str
    token_type: str

@app.get("/")
def read_root():
    return {"message": "Welcome to Aegis Mastery LMS API"}

# --- Auth Routes ---

@app.post("/auth/register")
def register(user: UserCreate, db: Session = Depends(get_db)):
    if user.role not in ["student", "lecturer", "admin"]:
        raise HTTPException(status_code=400, detail="Invalid role")

    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_pwd = auth.get_password_hash(user.password)
    new_user = models.User(
        email=user.email,
        hashed_password=hashed_pwd,
        role=user.role,
        pas=user.pas,
        vark_v=user.v,
        vark_a=user.a,
        vark_r=user.r,
        vark_k=user.k
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"message": "User created successfully"}

@app.post("/auth/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/users/me")
def get_me(current_user: models.User = Depends(auth.get_current_user)):
    return current_user

# --- Admin & Logic Routes ---

@app.get("/settings/registration")
def get_registration_settings(db: Session = Depends(get_db)):
    settings = db.query(models.WeightedSettings).first()
    if not settings:
        settings = models.WeightedSettings(w_prev=0.5, w_diag=0.5)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings

@app.get("/admin/settings")
def get_settings(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    auth.check_role(current_user, ["admin"])
    settings = db.query(models.WeightedSettings).first()
    if not settings:
        settings = models.WeightedSettings(w_prev=0.5, w_diag=0.5)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings

@app.patch("/admin/settings")
def update_settings(settings: SettingsUpdate, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    auth.check_role(current_user, ["admin"])
    db_settings = db.query(models.WeightedSettings).first()
    db_settings.w_prev = settings.w_prev
    db_settings.w_diag = settings.w_diag
    db.commit()
    return db_settings

@app.post("/student/diagnostic")
def submit_diagnostic(result: DiagnosticResult, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    check_user_access(current_user, result.user_id)
    user = db.query(models.User).filter(models.User.id == result.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    settings = db.query(models.WeightedSettings).first()
    if not settings:
        settings = models.WeightedSettings(w_prev=0.5, w_diag=0.5)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    
    expertise = logic.calculate_expertise(user.pas, result.score, settings.w_prev, settings.w_diag)
    # Update user state based on expertise (e.g., unlocking tracks)
    return {"expertise": expertise}

@app.get("/curriculum/{curriculum_id}/next")
async def get_next_lesson(curriculum_id: int, user_id: int, topic_idx: Optional[int] = None, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    check_user_access(current_user, user_id)
    user = db.query(models.User).filter(models.User.id == user_id).first()
    curriculum = db.query(models.CurriculumObject).filter(models.CurriculumObject.id == curriculum_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not curriculum:
        raise HTTPException(status_code=404, detail="Curriculum not found")
    
    # Get failed modalities from logs
    query = db.query(models.MasteryLog).filter(
        models.MasteryLog.user_id == user_id,
        models.MasteryLog.curriculum_id == curriculum_id,
        models.MasteryLog.score < 90.0
    )
    if topic_idx is not None:
        query = query.filter(models.MasteryLog.topic_idx == topic_idx)
        
    failed_logs = query.all()
    
    failed_modalities = [log.modality_used for log in failed_logs]
    
    vark = {
        'v': user.vark_v,
        'a': user.vark_a,
        'r': user.vark_r,
        'k': user.vark_k
    }
    
    identified_style = max(vark, key=vark.get)
    recommended = logic.get_recommended_modality(vark, failed_modalities)
    
    # Default content from top-level
    content_source = {
        "v": curriculum.modality_v,
        "a": curriculum.modality_a,
        "r": curriculum.modality_r,
        "k": curriculum.modality_k,
        "quiz": curriculum.quiz_questions
    }

    # Override if topic_idx is provided or if excel_data exists
    if curriculum.excel_data_json:
        idx = topic_idx if topic_idx is not None else 0
        if 0 <= idx < len(curriculum.excel_data_json):
            topic = curriculum.excel_data_json[idx]
            if 'materials' in topic:
                for mod in ['v', 'a', 'r', 'k', 'quiz']:
                    if topic['materials'].get(mod):
                        # If it's a file path, wrap it in a standard object
                        val = topic['materials'][mod]
                        if isinstance(val, str):
                            content_source[mod] = {"type": "file", "content": val}
                        else:
                            content_source[mod] = {"type": "json", "content": val}

    # Determine topic title for AI generation
    topic_title = curriculum.excel_data_json[topic_idx]['Topic'] if (curriculum.excel_data_json and topic_idx is not None and topic_idx < len(curriculum.excel_data_json)) else curriculum.title
    topic_group_title = None
    if curriculum.excel_data_json and topic_idx is not None and topic_idx < len(curriculum.excel_data_json):
        raw_title = curriculum.excel_data_json[topic_idx].get('Title', '')
        topic_group_title = raw_title if raw_title and raw_title.lower() != 'nan' else None
    # Inherit last non-null Title from earlier rows if current row has nan
    if not topic_group_title and curriculum.excel_data_json and topic_idx is not None:
        for i in range(topic_idx, -1, -1):
            raw_title = curriculum.excel_data_json[i].get('Title', '')
            if raw_title and raw_title.lower() != 'nan':
                topic_group_title = raw_title
                break

    # AI Fallback: Generate content if it's missing or a placeholder for the identified style
    final_content = content_source.get(identified_style)
    
    is_missing = not final_content or \
                (isinstance(final_content, dict) and 'content' in final_content and "Pending AI generation" in str(final_content['content'])) or \
                (isinstance(final_content, dict) and final_content.get('content') is None)

    if is_missing:
        # Use Gemini to generate missing content
        ai_generated = await ai_service.generate_modality_content_gemini(topic_title, identified_style)
        final_content = {"type": "ai_generated", "content": ai_generated.get('content', "Failed to generate AI content.")}

    content_source[identified_style] = final_content

    # AI Fallback: Generate quiz if missing or uses old letter-based answers (A/B/C/D)
    quiz_content = content_source.get("quiz")
    letter_map = {'A': 0, 'B': 1, 'C': 2, 'D': 3}

    needs_regeneration = not quiz_content or len(quiz_content) == 0

    # Normalize quiz_content to a list (it may be a dict with a 'questions' key)
    if quiz_content and not isinstance(quiz_content, list):
        if isinstance(quiz_content, dict):
            for key in ('questions', 'quiz', 'items'):
                if key in quiz_content and isinstance(quiz_content[key], list):
                    quiz_content = quiz_content[key]
                    break
            else:
                needs_regeneration = True  # Can't unwrap — regenerate
        else:
            needs_regeneration = True

    if not needs_regeneration and quiz_content:
        # Check if existing quiz uses letter answers instead of full text
        first_answer = quiz_content[0].get('answer', '') if isinstance(quiz_content, list) and quiz_content else ''
        if str(first_answer).strip().upper() in letter_map:
            # Try to normalize: replace letter answer with the actual option text
            normalized = []
            all_ok = True
            for q in quiz_content:
                opts = q.get('options', [])
                ans_letter = str(q.get('answer', '')).strip().upper()
                if ans_letter in letter_map and len(opts) > letter_map[ans_letter]:
                    normalized.append({**q, 'answer': opts[letter_map[ans_letter]]})
                else:
                    all_ok = False
                    break
            if all_ok:
                quiz_content = normalized
                # Persist the normalized version
                if curriculum.excel_data_json and topic_idx is not None and 0 <= topic_idx < len(curriculum.excel_data_json):
                    curriculum.excel_data_json[topic_idx].setdefault('materials', {})['quiz'] = quiz_content
                    from sqlalchemy.orm.attributes import flag_modified
                    flag_modified(curriculum, "excel_data_json")
                    db.commit()
            else:
                needs_regeneration = True  # Normalization failed, regenerate

    if needs_regeneration:
        quiz_content = await ai_service.generate_quiz_gemini(curriculum.title, topic_title)
        content_source["quiz"] = quiz_content

        # Persist the AI-generated quiz
        if curriculum.excel_data_json and topic_idx is not None and 0 <= topic_idx < len(curriculum.excel_data_json):
            topic_data = curriculum.excel_data_json[topic_idx]
            if 'materials' not in topic_data:
                topic_data['materials'] = {}
            topic_data['materials']['quiz'] = quiz_content
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(curriculum, "excel_data_json")
            db.commit()

    return {
        "modality": identified_style,
        "recommended_modality": recommended,
        "content": final_content,
        "all_content": content_source,
        "quiz": quiz_content,
        "is_scaffolding": identified_style != recommended,
        "topic_title": topic_title,
        "topic_group_title": topic_group_title,
        "curriculum_title": curriculum.title
    }

@app.get("/student/{user_id}/profile")
def get_student_profile(user_id: int, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    check_user_access(current_user, user_id)
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@app.get("/student/{user_id}/curriculum/{curriculum_id}/progress")
def get_student_progress(user_id: int, curriculum_id: int, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    check_user_access(current_user, user_id)
    logs = db.query(models.MasteryLog).filter(
        models.MasteryLog.user_id == user_id,
        models.MasteryLog.curriculum_id == curriculum_id
    ).all()
    
    progress = {}
    for log in logs:
        if log.topic_idx is not None:
            if log.topic_idx not in progress:
                progress[log.topic_idx] = log.score
            else:
                progress[log.topic_idx] = max(progress[log.topic_idx], log.score)
                
    return progress

@app.post("/student/{user_id}/telemetry")
def update_telemetry(user_id: int, telemetry: TelemetryUpdate, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    check_user_access(current_user, user_id)
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    vark = {
        'v': user.vark_v,
        'a': user.vark_a,
        'r': user.vark_r,
        'k': user.vark_k
    }
    
    # Simple logic: increase modality if engagement is high
    intensity = 0.01 * (telemetry.engagement_time / 60) # 0.01 per minute
    new_vark = logic.refine_vark(vark, telemetry.modality.lower(), intensity)
    
    user.vark_v = new_vark['v']
    user.vark_a = new_vark['a']
    user.vark_r = new_vark['r']
    user.vark_k = new_vark['k']
    
    db.commit()
    return new_vark

@app.post("/curriculum/submit")
def submit_mastery(submission: MasterySubmission, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    check_user_access(current_user, submission.user_id)
    user = db.query(models.User).filter(models.User.id == submission.user_id).first()
    curriculum = db.query(models.CurriculumObject).filter(models.CurriculumObject.id == submission.curriculum_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not curriculum:
        raise HTTPException(status_code=404, detail="Curriculum not found")
    # Save log
    db_log = models.MasteryLog(
        user_id=submission.user_id,
        curriculum_id=submission.curriculum_id,
        topic_idx=submission.topic_idx,
        score=submission.score,
        modality_used=submission.modality,
        feedback=submission.feedback
    )
    db.add(db_log)
    db.flush() # Ensure the new log is considered in the max() query
    
    from sqlalchemy import func
    max_v = db.query(func.max(models.MasteryLog.score)).filter_by(user_id=submission.user_id, modality_used='v').scalar() or 0.0
    max_a = db.query(func.max(models.MasteryLog.score)).filter_by(user_id=submission.user_id, modality_used='a').scalar() or 0.0
    max_r = db.query(func.max(models.MasteryLog.score)).filter_by(user_id=submission.user_id, modality_used='r').scalar() or 0.0
    max_k = db.query(func.max(models.MasteryLog.score)).filter_by(user_id=submission.user_id, modality_used='k').scalar() or 0.0
    
    sum_max = max_v + max_a + max_r + max_k
    if sum_max > 0:
        user.vark_v = max_v / sum_max
        user.vark_a = max_a / sum_max
        user.vark_r = max_r / sum_max
        user.vark_k = max_k / sum_max
    
    # Check mastery
    is_mastered = logic.check_mastery(submission.score)
    
    db.commit()
    return {"is_mastered": is_mastered, "score": submission.score}

@app.post("/curriculum/generate")
async def generate_curriculum(request: CurriculumGenerateRequest, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    auth.check_role(current_user, ["lecturer", "admin"])
    # AI Transformation
    try:
        modalities = await ai_service.generate_multimodal_content(request.text_content)
        is_valid = await ai_service.equivalency_auditor(request.text_content, modalities)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI service unavailable: {str(exc)}")
    
    if not is_valid:
        raise HTTPException(status_code=400, detail="AI generation failed equivalency audit")
        
    db_curriculum = models.CurriculumObject(
        title=request.title,
        code=request.code,
        level=request.level,
        description=request.description,
        modality_v=modalities['v'],
        modality_a=modalities['a'],
        modality_r=modalities['r'],
        modality_k=modalities['k']
    )
    db.add(db_curriculum)
    db.commit()
    db.refresh(db_curriculum)
    return db_curriculum

@app.get("/lecturer/intervention-heatmap")
def get_intervention_heatmap(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    auth.check_role(current_user, ["lecturer", "admin"])
    # Flag students who fail across >= 2 modalities
    logs = db.query(models.MasteryLog).filter(models.MasteryLog.score < 90.0).all()
    return logs

@app.get("/lecturer/class-profile")
def get_class_profile(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    auth.check_role(current_user, ["lecturer", "admin"])
    users = db.query(models.User).filter(models.User.role == "student").all()
    return users

@app.get("/lecturer/class-mastery-summary")
def get_class_mastery_summary(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    auth.check_role(current_user, ["lecturer", "admin"])
    logs = db.query(models.MasteryLog).all()
    if not logs:
        return {"average_mastery": 0, "attempts": 0}
    average = sum(log.score for log in logs) / len(logs)
    return {"average_mastery": round(average), "attempts": len(logs)}

@app.get("/curriculum/list")
def list_curriculum(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    return db.query(models.CurriculumObject).all()

@app.get("/admin/users")
def list_users(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    auth.check_role(current_user, ["admin"])
    return db.query(models.User).all()

@app.delete("/admin/users/{user_id}")
def delete_user(user_id: int, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    auth.check_role(current_user, ["admin"])
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(db_user)
    db.commit()
    return {"message": "User deleted successfully"}

class PasswordUpdate(BaseModel):
    new_password: str

@app.patch("/admin/users/{user_id}/password")
def update_user_password(user_id: int, update: PasswordUpdate, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    auth.check_role(current_user, ["admin"])
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    db_user.hashed_password = auth.get_password_hash(update.new_password)
    db.commit()
    return {"message": "Password updated successfully"}

# --- Module Management ---

class CurriculumCreate(BaseModel):
    title: str
    code: str
    level: str
    description: str

@app.post("/admin/curriculum")
def create_curriculum(item: CurriculumCreate, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    auth.check_role(current_user, ["lecturer", "admin"])
    # Initialize with default empty modalities (to be filled by AI later)
    db_item = models.CurriculumObject(
        **item.dict(),
        modality_v={"type": "visual", "content": "Pending AI generation..."},
        modality_a={"type": "auditory", "content": "Pending AI generation..."},
        modality_r={"type": "reading", "content": "Pending AI generation..."},
        modality_k={"type": "kinesthetic", "content": "Pending AI generation..."}
    )
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item

@app.patch("/admin/curriculum/{item_id}")
def update_curriculum(item_id: int, item: CurriculumCreate, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    auth.check_role(current_user, ["lecturer", "admin"])
    db_item = db.query(models.CurriculumObject).filter(models.CurriculumObject.id == item_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Module not found")
    
    for key, value in item.dict().items():
        setattr(db_item, key, value)
    
    db.commit()
    db.refresh(db_item)
    return db_item

@app.delete("/admin/curriculum/{item_id}")
def delete_curriculum(item_id: int, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    auth.check_role(current_user, ["lecturer", "admin"])
    db_item = db.query(models.CurriculumObject).filter(models.CurriculumObject.id == item_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Module not found")
    db.delete(db_item)
    db.commit()
    return {"message": "Module deleted successfully"}

@app.post("/lecturer/curriculum/{item_id}/upload")
async def upload_curriculum_excel(item_id: int, file: UploadFile = File(...), current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    auth.check_role(current_user, ["lecturer", "admin"])
    
    db_item = db.query(models.CurriculumObject).filter(models.CurriculumObject.id == item_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Module not found")
    
    try:
        # Reset file pointer to ensure it's readable from the start
        await file.seek(0)
        contents = await file.read()
        
        # 1. Save the file locally for persistence
        file_path = upload_path(f"excel_{item_id}", file.filename)
        with open(file_path, "wb") as buffer:
            buffer.write(contents)
        
        db_item.excel_path = file_path
        
        # 2. Parse from memory
        df = pd.read_excel(io.BytesIO(contents), engine='openpyxl')
        df = df.fillna('')
        
        # Replace all NaN with empty strings
        df = df.fillna('')
        
        # Extract specific columns for display
        required_cols = ['Chapter', 'Title', 'Topic', 'Topic_Outcome', 'Material']
        col_map = {c.lower(): c for c in df.columns}
        available_cols = []
        for rc in required_cols:
            if rc.lower() in col_map:
                available_cols.append(col_map[rc.lower()])
        
        # Convert and standardize
        extracted_data = df[available_cols].to_dict(orient='records')
        standardized_data = []
        for row in extracted_data:
            new_row = {}
            for rc in required_cols:
                # Find matching key in row (case insensitive)
                actual_key = next((k for k in row.keys() if k.lower() == rc.lower()), None)
                val = row[actual_key] if actual_key else ''
                # Convert everything to string and handle 'nan' string just in case
                val_str = str(val) if val != '' else ''
                if val_str.lower() == 'nan': val_str = ''
                new_row[rc] = val_str
            
            # Initialize empty materials object if not present
            if 'materials' not in new_row:
                new_row['materials'] = {"v": None, "a": None, "r": None, "k": None, "quiz": []}
            standardized_data.append(new_row)

        db_item.excel_data_json = standardized_data
        db.commit()
        
        return {"message": "Success", "data": standardized_data}
    except Exception as e:
        import traceback
        err_msg = f"Excel Failure: {str(e)}"
        print(f"ERROR: {err_msg}")
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=err_msg)

@app.post("/lecturer/curriculum/{item_id}/assets/{modality}")
async def upload_curriculum_asset(item_id: int, modality: str, file: UploadFile = File(...), current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    auth.check_role(current_user, ["lecturer", "admin"])
    db_item = db.query(models.CurriculumObject).filter(models.CurriculumObject.id == item_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Module not found")
    
    if modality not in ["v", "a", "r", "k"]:
        raise HTTPException(status_code=400, detail="Invalid modality")

    file_path = upload_path(f"{modality}_{item_id}", file.filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    asset_data = {"type": "file", "content": f"/uploads/{os.path.basename(file_path)}", "original_name": file.filename}
    
    if modality == 'v': db_item.modality_v = asset_data
    elif modality == 'a': db_item.modality_a = asset_data
    elif modality == 'r': db_item.modality_r = asset_data
    elif modality == 'k': db_item.modality_k = asset_data
    
    db.commit()
    return {"message": f"{modality.upper()} asset uploaded.", "url": asset_data['content']}

class QuizUpdate(BaseModel):
    questions: List[dict]

@app.post("/lecturer/curriculum/{item_id}/quiz")
def update_quiz(item_id: int, quiz: QuizUpdate, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    auth.check_role(current_user, ["lecturer", "admin"])
    db_item = db.query(models.CurriculumObject).filter(models.CurriculumObject.id == item_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Module not found")
    db_item.quiz_questions = quiz.questions
    db.commit()
    return {"message": "Quiz questions updated."}

@app.post("/lecturer/curriculum/{item_id}/topic/{topic_idx}/material/{m_type}")
async def upload_topic_material(item_id: int, topic_idx: int, m_type: str, file: UploadFile = File(...), current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    auth.check_role(current_user, ["lecturer", "admin"])
    db_item = db.query(models.CurriculumObject).filter(models.CurriculumObject.id == item_id).first()
    
    if not db_item or not db_item.excel_data_json:
        raise HTTPException(status_code=404, detail="Module or curriculum data not found")
    
    if m_type not in ["v", "a", "r", "k", "quiz"]:
        raise HTTPException(status_code=400, detail="Invalid material type")
    
    # Update JSON data
    data = list(db_item.excel_data_json)
    if topic_idx < 0 or topic_idx >= len(data):
        raise HTTPException(status_code=400, detail="Invalid topic index")

    file_path = upload_path(f"material_{item_id}_{topic_idx}_{m_type}", file.filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    topic = data[topic_idx]
    if 'materials' not in topic:
        topic['materials'] = {"v": None, "a": None, "r": None, "k": None, "quiz": []}
    
    if m_type == 'quiz':
        # Parse Quiz Excel
        try:
            quiz_df = pd.read_excel(io.BytesIO(open(file_path, "rb").read()), engine='openpyxl')
            quiz_df = quiz_df.fillna('')
            questions = []
            for _, r in quiz_df.iterrows():
                questions.append({
                    "question": str(r.get('Question', '')),
                    "options": [str(r.get('A', '')), str(r.get('B', '')), str(r.get('C', '')), str(r.get('D', ''))],
                    "answer": str(r.get('Answer', ''))
                })
            topic['materials']['quiz'] = questions
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Quiz Parse Error: {str(e)}")
    else:
        topic['materials'][m_type] = f"/uploads/{os.path.basename(file_path)}"
    
    # Force SQLAlchemy to detect the change in the JSON list
    from sqlalchemy.orm.attributes import flag_modified
    db_item.excel_data_json = data
    flag_modified(db_item, "excel_data_json")
    
    db.commit()
    return {"message": f"{m_type.upper()} updated", "url": topic['materials'].get(m_type) if m_type != 'quiz' else "JSON_DATA"}
