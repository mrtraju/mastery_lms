@app.post("/lecturer/curriculum/{item_id}/upload")
async def upload_curriculum_excel(item_id: int, file: UploadFile = File(...), current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    auth.check_role(current_user, ["lecturer", "admin"])
    
    db_item = db.query(models.CurriculumObject).filter(models.CurriculumObject.id == item_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Module not found")
    
    try:
        # 1. Save the file locally
        file_ext = os.path.splitext(file.filename)[1]
        file_path = f"uploads/excel_{item_id}{file_ext}"
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        db_item.excel_path = file_path
        
        # 2. Parse and map logic
        with open(file_path, "rb") as f:
            df = pd.read_excel(f)
            for _, row in df.iterrows():
                mod = str(row['Modality']).strip().lower()
                m_type = str(row['Type']).strip()
                m_content = str(row['Content']).strip()
                payload = {"type": m_type, "content": m_content}
                if mod == 'visual': db_item.modality_v = payload
                elif mod == 'auditory': db_item.modality_a = payload
                elif mod == 'reading': db_item.modality_r = payload
                elif mod == 'kinesthetic': db_item.modality_k = payload
        
        db.commit()
        return {"message": "Excel stored and curriculum mapped.", "path": file_path}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error: {str(e)}")

@app.post("/lecturer/curriculum/{item_id}/assets/{modality}")
async def upload_curriculum_asset(item_id: int, modality: str, file: UploadFile = File(...), current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    auth.check_role(current_user, ["lecturer", "admin"])
    db_item = db.query(models.CurriculumObject).filter(models.CurriculumObject.id == item_id).first()
    
    file_ext = os.path.splitext(file.filename)[1]
    file_path = f"uploads/{modality}_{item_id}{file_ext}"
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
    db_item.quiz_questions = quiz.questions
    db.commit()
    return {"message": "Quiz questions updated."}
