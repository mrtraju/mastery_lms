from database import SessionLocal, engine
import models
import auth

models.Base.metadata.create_all(bind=engine)

db = SessionLocal()

# Add Admin Settings
if not db.query(models.WeightedSettings).first():
    db.add(models.WeightedSettings(w_prev=0.5, w_diag=0.5))

# --- Sample Users ---
users = [
    {
        "email": "admin@aegis.com",
        "password": "admin123",
        "role": "admin"
    },
    {
        "email": "lecturer@aegis.com",
        "password": "lecturer123",
        "role": "lecturer"
    },
    {
        "email": "student@aegis.com",
        "password": "student123",
        "role": "student",
        "pas": 85.0,
        "vark": {"v": 0.7, "a": 0.1, "r": 0.1, "k": 0.1}
    }
]

for user_data in users:
    if not db.query(models.User).filter(models.User.email == user_data["email"]).first():
        vark = user_data.get("vark", {"v": 0.25, "a": 0.25, "r": 0.25, "k": 0.25})
        db.add(models.User(
            email=user_data["email"],
            hashed_password=auth.get_password_hash(user_data["password"]),
            role=user_data["role"],
            pas=user_data.get("pas", 0.0),
            vark_v=vark["v"],
            vark_a=vark["a"],
            vark_r=vark["r"],
            vark_k=vark["k"]
        ))

# --- Sample Curriculum ---
if not db.query(models.CurriculumObject).filter(models.CurriculumObject.title == "Binary Number System").first():
    db.add(models.CurriculumObject(
        title="Binary Number System",
        description="Core concepts of Base-2 representation in Discrete Mathematics.",
        modality_v={
            "type": "infographic", 
            "content": "A high-resolution diagram showing the powers of 2 (1, 2, 4, 8, 16...) and how bits align to represent decimal 10 (1010)."
        },
        modality_a={
            "type": "lecture_snippet", 
            "content": "Audio: 'Think of binary like a series of light switches. ON is 1, OFF is 0. Each switch to the left is worth double the one to its right...'"
        },
        modality_r={
            "type": "technical_text", 
            "content": "The binary system is a positional notation with a radix of 2. It was popularized by Gottfried Wilhelm Leibniz in the 17th century and forms the basis of all modern computing architecture."
        },
        modality_k={
            "type": "interactive_lab", 
            "content": "Challenge: Flip the switches (0/1) to construct the number 25. Hint: 16 + 8 + 1."
        }
    )
)

if not db.query(models.CurriculumObject).filter(models.CurriculumObject.title == "Network Security").first():
    db.add(models.CurriculumObject(
        title="Network Security",
        description="Introduction to network security concepts.",
        modality_v={"type": "diagram", "content": "Diagram of a firewall and DMZ architecture."},
        modality_a={"type": "audio", "content": "Podcast: 'The 7 Layers of Cyber Defense'."},
        modality_r={"type": "text", "content": "Summary of OSI model security protocols."},
        modality_k={"type": "lab", "content": "Interactive Lab: Configure a pfSense Firewall."}
    ))

db.commit()
db.close()
print("Sample users and curriculum inserted successfully.")
