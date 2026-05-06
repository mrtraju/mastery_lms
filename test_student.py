from pathlib import Path

import requests


BASE_URL = "http://localhost:8000"
ROOT = Path(__file__).resolve().parent


def login(email: str, password: str) -> str:
    response = requests.post(
        f"{BASE_URL}/auth/login",
        data={"username": email, "password": password},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_student_flow():
    lecturer_token = login("lecturer@aegis.com", "lecturer123")
    student_token = login("student@aegis.com", "student123")

    curriculum_response = requests.get(
        f"{BASE_URL}/curriculum/list",
        headers=auth_headers(student_token),
        timeout=10,
    )
    curriculum_response.raise_for_status()
    curriculums = curriculum_response.json()
    if not curriculums:
        print("No curriculum found.")
        return

    curriculum_id = curriculums[0]["id"]
    print(f"Using curriculum ID: {curriculum_id}")

    excel_path = ROOT / "backend" / "uploads" / "excel_1.xlsx"
    if excel_path.exists():
        with excel_path.open("rb") as file_handle:
            upload_response = requests.post(
                f"{BASE_URL}/lecturer/curriculum/{curriculum_id}/upload",
                files={"file": file_handle},
                headers=auth_headers(lecturer_token),
                timeout=20,
            )
        print("Excel upload:", upload_response.status_code, upload_response.json())

    material_path = ROOT / "backend" / "sample_materials" / "reading_intro.pdf"
    if material_path.exists():
        with material_path.open("rb") as file_handle:
            material_response = requests.post(
                f"{BASE_URL}/lecturer/curriculum/{curriculum_id}/topic/0/material/r",
                files={"file": file_handle},
                headers=auth_headers(lecturer_token),
                timeout=20,
            )
        print("Topic material upload:", material_response.status_code, material_response.json())

    me_response = requests.get(
        f"{BASE_URL}/users/me",
        headers=auth_headers(student_token),
        timeout=10,
    )
    me_response.raise_for_status()
    student_id = me_response.json()["id"]

    lesson_response = requests.get(
        f"{BASE_URL}/curriculum/{curriculum_id}/next",
        params={"user_id": student_id, "topic_idx": 0},
        headers=auth_headers(student_token),
        timeout=10,
    )
    print("Student lesson:", lesson_response.status_code, lesson_response.json())


if __name__ == "__main__":
    test_student_flow()
