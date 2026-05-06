import os
import wave
import struct
import math
import pandas as pd

# Create directory
out_dir = "sample_materials"
os.makedirs(out_dir, exist_ok=True)

# 1. Kinesthetic File (Python Script)
k_script = """# Number Base System - Interactive Lab
def decimal_to_binary(n):
    return bin(n)[2:]

print("Welcome to the Kinesthetic Lab!")
while True:
    try:
        num = int(input("Enter a decimal number (or -1 to quit): "))
        if num == -1: break
        print(f"Binary representation: {decimal_to_binary(num)}")
    except:
        print("Please enter a valid integer.")
"""
with open(os.path.join(out_dir, "kinesthetic_intro.py"), "w") as f:
    f.write(k_script)

# 2. MCQ Excel File
quiz_data = [
    {"Question": "What is the base of the decimal number system?", "A": "2", "B": "8", "C": "10", "D": "16", "Answer": "C"},
    {"Question": "Which digits are used in the binary system?", "A": "0 to 9", "B": "0 and 1", "C": "1 and 2", "D": "0 to 7", "Answer": "B"},
    {"Question": "What is the binary representation of decimal 2?", "A": "0", "B": "1", "C": "10", "D": "11", "Answer": "C"},
    {"Question": "The octal system uses base:", "A": "2", "B": "8", "C": "10", "D": "16", "Answer": "B"},
    {"Question": "Which letter represents the value 10 in hexadecimal?", "A": "A", "B": "B", "C": "E", "D": "F", "Answer": "A"},
    {"Question": "What is decimal 10 in binary?", "A": "1000", "B": "1001", "C": "1010", "D": "1011", "Answer": "C"},
    {"Question": "Hexadecimal uses how many unique symbols?", "A": "8", "B": "10", "C": "16", "D": "32", "Answer": "C"},
    {"Question": "Convert binary 11 to decimal.", "A": "1", "B": "2", "C": "3", "D": "4", "Answer": "C"},
    {"Question": "Which system is most commonly used directly by computer hardware?", "A": "Decimal", "B": "Hexadecimal", "C": "Octal", "D": "Binary", "Answer": "D"},
    {"Question": "The prefix 'hex' refers to:", "A": "6", "B": "8", "C": "16", "D": "10", "Answer": "C"}
]
df = pd.DataFrame(quiz_data)
df.to_excel(os.path.join(out_dir, "quiz_intro.xlsx"), index=False)

# 3. Audio File (Dummy WAV)
audio_path = os.path.join(out_dir, "audio_intro.wav")
sample_rate = 44100.0
duration = 5.0 # seconds (using 5 seconds instead of 5 mins to save space, user can test upload with it)
frequency = 440.0
with wave.open(audio_path, 'w') as wav_file:
    wav_file.setnchannels(1)
    wav_file.setsampwidth(2)
    wav_file.setframerate(int(sample_rate))
    for i in range(int(duration * sample_rate)):
        value = int(32767.0*math.cos(frequency*math.pi*float(i)/float(sample_rate)))
        data = struct.pack('<h', value)
        wav_file.writeframesraw(data)

# Try generating PDF using reportlab if available
try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter

    # 4. Slides PDF (10 pages)
    c = canvas.Canvas(os.path.join(out_dir, "slides_intro.pdf"), pagesize=letter)
    for i in range(1, 11):
        c.setFont("Helvetica-Bold", 36)
        c.drawString(100, 600, f"Number Base System")
        c.setFont("Helvetica", 24)
        c.drawString(100, 550, f"Slide {i} of 10")
        c.showPage()
    c.save()

    # 5. Reading PDF (5 pages)
    c2 = canvas.Canvas(os.path.join(out_dir, "reading_intro.pdf"), pagesize=letter)
    for i in range(1, 6):
        c2.setFont("Helvetica-Bold", 24)
        c2.drawString(50, 700, f"Introduction to Number Bases - Page {i}")
        c2.setFont("Helvetica", 12)
        text = c2.beginText(50, 650)
        text.textLines(
            "A number base is the number of distinct symbols used to represent numbers.\n"
            "For example, the decimal system uses 10 symbols (0-9).\n"
            "The binary system uses 2 symbols (0, 1).\n"
            "Understanding bases is crucial for computer science."
        )
        c2.drawText(text)
        c2.showPage()
    c2.save()
    print("Successfully generated all sample files including PDFs.")

except ImportError:
    print("Reportlab not installed. Creating simple text files as PDF placeholders.")
    with open(os.path.join(out_dir, "slides_intro.pdf"), "w") as f:
        f.write("Please install reportlab to generate real PDFs.")
    with open(os.path.join(out_dir, "reading_intro.pdf"), "w") as f:
        f.write("Please install reportlab to generate real PDFs.")

print(f"Sample files generated in: {os.path.abspath(out_dir)}")
