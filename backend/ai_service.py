import asyncio
import json
import os
from typing import Dict, List

from openai import OpenAI
from pydantic import BaseModel, Field

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


# Groq Configuration (Primary)
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
client_groq = OpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1") if GROQ_API_KEY else None

# OpenAI Configuration (Fallback)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
client_openai = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


def _get_active_client():
    """Returns the primary (Groq) or fallback (OpenAI) client."""
    if client_groq:
        return client_groq, GROQ_MODEL
    if client_openai:
        return client_openai, OPENAI_MODEL
    return None, None


class ModalityContent(BaseModel):
    type: str = Field(description="Short content type label for the modality.")
    title: str = Field(description="Learner-facing title.")
    content: str = Field(description="Complete learner-facing content for this modality.")
    learning_objectives: List[str] = Field(description="Core objectives covered by this modality.")
    assessment_focus: List[str] = Field(description="Concepts the quiz should assess after this content.")


class MultimodalContent(BaseModel):
    v: ModalityContent = Field(description="Visual learning version.")
    a: ModalityContent = Field(description="Auditory learning version.")
    r: ModalityContent = Field(description="Reading and writing learning version.")
    k: ModalityContent = Field(description="Kinesthetic learning version.")


class AuditResult(BaseModel):
    is_valid: bool
    coverage_score: float = Field(description="0 to 1 score for learning-objective equivalence.")
    missing_or_weak_points: List[str]
    recommendations: List[str]


def _fallback_multimodal_content(text_content: str) -> Dict[str, dict]:
    summary = text_content.strip()[:1200] or "No source content supplied."
    return {
        "v": {
            "type": "visual",
            "title": "Visual concept map",
            "content": f"Create a diagram that maps the key ideas, relationships, examples, and sequence from this source material: {summary}",
            "learning_objectives": ["Identify the key ideas and relationships in the source material."],
            "assessment_focus": ["Recognize the visual structure of the core concept."],
        },
        "a": {
            "type": "auditory",
            "title": "Guided audio explanation",
            "content": f"Explain the topic aloud in a short lecture script, using examples and transitions that preserve the source material: {summary}",
            "learning_objectives": ["Explain the key ideas using spoken reasoning and examples."],
            "assessment_focus": ["Recall the spoken explanation and apply the examples."],
        },
        "r": {
            "type": "reading",
            "title": "Structured reading notes",
            "content": f"Read this concise study note, then restate the definitions, steps, and examples in your own words: {summary}",
            "learning_objectives": ["Read, define, and summarize the central concepts."],
            "assessment_focus": ["Match definitions and apply written procedures."],
        },
        "k": {
            "type": "kinesthetic",
            "title": "Hands-on practice activity",
            "content": f"Complete a hands-on task that applies the source material. Build, solve, or simulate the main idea, then explain what changed and why: {summary}",
            "learning_objectives": ["Apply the concept through an active task or scenario."],
            "assessment_focus": ["Demonstrate the concept through practical decision-making."],
        },
    }


def _parse_with_chat_completions(ai_client, model, model_cls: type[BaseModel], system_prompt: str, user_prompt: str):
    response = ai_client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": f"{system_prompt}\nReturn valid JSON that matches this schema: {model_cls.model_json_schema()}"},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content or "{}"
    return model_cls.model_validate(json.loads(content))


def _run_structured_completion(model_cls: type[BaseModel], system_prompt: str, user_prompt: str):
    ai_client, model = _get_active_client()
    if ai_client is None:
        raise RuntimeError("No AI client configured. Set GROQ_API_KEY or OPENAI_API_KEY.")
    return _parse_with_chat_completions(ai_client, model, model_cls, system_prompt, user_prompt)


async def generate_multimodal_content(text_content: str) -> Dict[str, dict]:
    """
    Transform source learning content into schema-valid VARK modality blocks using Groq (primary) or OpenAI (fallback).
    """
    if not text_content.strip():
        raise ValueError("text_content is required for AI curriculum generation")

    ai_client, model = _get_active_client()
    if ai_client is None:
        return _fallback_multimodal_content(text_content)

    system_prompt = (
        "You are a highly experienced university lecturer and instructional designer with over 20 years of teaching expertise. "
        "Your role is to transform raw source material into rich, pedagogically sound learning content that resonates with students across all learning styles. "
        "You understand how students think, where they struggle, and how to scaffold knowledge effectively. "
        "Every version you produce must be instructionally equivalent — covering the same learning objectives — but adapted to the natural strengths of each VARK modality. "
        "Write with clarity, depth, and the authority of a seasoned educator. Return only the requested structured data."
    )
    user_prompt = f"""
Source learning material provided by the course instructor:
{text_content}

As an experienced teacher, transform the above material into four modality-specific versions:

1. VISUAL — Design a storyboard for an infographic or diagram. Describe each visual element, its label, and how it connects to the next. Use spatial reasoning to show relationships, hierarchies, and flows.

2. AUDITORY — Write a lecture script as if you are speaking directly to a class. Use a conversational tone, rhetorical questions, verbal signposting ("First...", "Now here's the important part..."), and memorable analogies.

3. READING/WRITING — Produce well-structured study notes. Use clear headings, bullet-pointed definitions, step-by-step explanations, and a summary of key takeaways. Suitable for a student to annotate and review.

4. KINESTHETIC — Design a hands-on activity, lab exercise, or real-world scenario. The student must take specific actions, make decisions, observe results, and reflect. Ground every step in application.

Ensure all four versions teach the exact same core learning objectives and prepare students for the same mastery assessment.
"""

    parsed = await asyncio.to_thread(
        _run_structured_completion,
        MultimodalContent,
        system_prompt,
        user_prompt,
    )
    return parsed.model_dump()


async def equivalency_auditor(original: str, generated: Dict[str, dict]) -> bool:
    """
    Verify that generated VARK versions preserve the original learning objectives.
    """
    ai_client, _ = _get_active_client()
    if ai_client is None:
        return True

    system_prompt = (
        "You are a senior academic reviewer and curriculum quality assurance specialist. "
        "Your job is to audit whether AI-generated VARK learning materials are instructionally equivalent to the original source material. "
        "You assess with the rigour of an experienced examiner: checking that learning objectives are preserved, key concepts are not distorted, "
        "and that each modality version could support the same mastery assessment as the source. "
        "Be strict. Mark invalid if any modality omits essential concepts, introduces inaccuracies, or weakens the instructional integrity."
    )
    user_prompt = f"""
Original source material (as provided by the course instructor):
{original}

AI-generated VARK materials (to be audited):
{json.dumps(generated, ensure_ascii=False)}

Audit each modality against the source. For your structured response:
- Set is_valid to true ONLY if ALL four modalities are instructionally equivalent to the source.
- Score coverage_score from 0.0 (no overlap) to 1.0 (perfect equivalence).
- List any missing or weakened concepts under missing_or_weak_points.
- Provide actionable recommendations for improvement.
"""

    parsed = await asyncio.to_thread(
        _run_structured_completion,
        AuditResult,
        system_prompt,
        user_prompt,
    )
    return bool(parsed.is_valid and parsed.coverage_score >= 0.8)


async def generate_modality_content(topic: str, modality: str) -> Dict:
    """
    Generate learning content for a specific topic and VARK modality.
    Uses Groq as the primary engine, falls back to OpenAI.
    """
    modality_instructions = {
        'v': (
            "VISUAL LEARNING CONTENT\n"
            "Create a rich storyboard description for a diagram or infographic. "
            "Label every component clearly. Use arrows, hierarchies, or colour-coded zones to show structure and flow. "
            "Describe each visual element as if guiding an illustrator — what the student sees and what each part means."
        ),
        'a': (
            "AUDITORY LEARNING CONTENT\n"
            "Write a full lecture script as if you are addressing a live classroom. "
            "Open with a hook or a thought-provoking question. Use verbal signposting ('First...', 'Now pay close attention here...', 'To summarise...'). "
            "Include relatable analogies, rhetorical questions, and a confident, warm tone throughout."
        ),
        'r': (
            "READING/WRITING LEARNING CONTENT\n"
            "Produce structured academic study notes. Use numbered sections with bold headings, bullet-pointed definitions, "
            "step-by-step procedures, worked examples, and a concise summary. "
            "The student should be able to annotate and revise from these notes alone."
        ),
        'k': (
            "KINESTHETIC LEARNING CONTENT\n"
            "Design a practical, action-based learning activity. Give the student a clear scenario or problem, "
            "then walk them through specific steps they must physically perform, calculate, build, or simulate. "
            "Include decision points, expected outcomes, and reflection questions after each key action."
        )
    }

    system_prompt = (
        "You are a highly experienced teacher and subject matter expert with decades of classroom and curriculum design experience. "
        "You have a deep understanding of how students learn best and you write content that is clear, engaging, accurate, and pedagogically rich. "
        "Your content should feel like it was written by a real educator — not a generic AI assistant. "
        "Always respond in valid JSON format with keys: type, title, content."
    )

    user_prompt = f"""
You are preparing learning material for a student studying the following:
Topic: {topic}

Delivery Format Required:
{modality_instructions.get(modality, f'General explanation of: {topic}')}

Instructions:
- Write as an experienced, passionate teacher who genuinely wants the student to succeed.
- Make the content thorough, accurate, and curriculum-aligned.
- Avoid generic filler. Every sentence must add instructional value.
- The content should be complete enough for a student to learn from without any other resource.

Return ONLY a JSON object:
{{
  "type": "<short label, e.g. visual_storyboard / lecture_script / study_notes / lab_activity>",
  "title": "<an engaging, learner-facing title for this material>",
  "content": "<the full, rich educational content>"
}}
"""

    # Try Groq first
    if client_groq:
        try:
            print(f"DEBUG: Generating modality content via Groq ({GROQ_MODEL}) for topic: {topic}")
            response = await asyncio.to_thread(
                client_groq.chat.completions.create,
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"}
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"Groq modality content error: {e}")

    # Fallback to OpenAI
    if client_openai:
        try:
            print(f"DEBUG: Falling back to OpenAI ({OPENAI_MODEL}) for topic: {topic}")
            response = await asyncio.to_thread(
                client_openai.chat.completions.create,
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"}
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"OpenAI modality content error: {e}")

    return {
        "type": "error",
        "title": "AI Generation Failed",
        "content": f"No AI service available to generate content for: {topic}. Please set GROQ_API_KEY in your .env file."
    }


# Keep old name as alias so existing main.py calls still work
generate_modality_content_gemini = generate_modality_content


async def generate_quiz(curriculum_title: str, topic_title: str) -> list:
    """
    Generates a 10-question MCQ quiz using Groq (primary) or OpenAI (fallback).
    Includes validation: exactly 10 questions, 4 options each, answer present in options.
    """
    system_prompt = (
        "You are an experienced university examiner and teacher with deep expertise in designing assessments that truly test student understanding. "
        "You do not write trick questions or trivial recall questions. Instead, you craft questions that probe conceptual understanding, "
        "application of knowledge, and analytical thinking — the kinds of questions that distinguish students who truly understand from those who merely memorised. "
        "Every question you write is precise, unambiguous, and directly tied to the specific topic being assessed. "
        "Always respond in valid JSON format only."
    )

    user_prompt = f"""
You are setting a 10-question Multiple Choice Quiz for the following:
Curriculum / Subject: {curriculum_title}
Specific Topic Being Assessed: {topic_title}

Your assessment design principles:
1. Questions must be STRICTLY about the specific topic above — no generic or off-topic questions.
2. Cover a range of Bloom's taxonomy levels: recall (2 Qs), comprehension (3 Qs), application (3 Qs), and analysis (2 Qs).
3. Each question must have EXACTLY 4 options (A, B, C, D style content — but written out as full text, not letters).
4. Distractors (wrong answers) must be plausible — common misconceptions or related-but-incorrect ideas, not obviously wrong.
5. The correct answer must appear verbatim as one of the 4 options.
6. Do not repeat the same concept twice across questions.

Return a JSON object with a key "questions" containing an array of exactly 10 objects.
Each object must follow this format:
{{
    "question": "Full question text ending with a question mark?",
    "options": ["Correct or plausible option 1", "Correct or plausible option 2", "Correct or plausible option 3", "Correct or plausible option 4"],
    "answer": "The exact text of the correct option from the options array"
}}
"""

    data = None

    # Try Groq first
    if client_groq:
        try:
            print(f"DEBUG: Generating quiz via Groq ({GROQ_MODEL}) for topic: {topic_title}")
            response = await asyncio.to_thread(
                client_groq.chat.completions.create,
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"}
            )
            data = json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"Groq Quiz Generation Error: {e}")

    # Fallback to OpenAI
    if not data and client_openai:
        try:
            print(f"DEBUG: Falling back to OpenAI ({OPENAI_MODEL}) for quiz on topic: {topic_title}")
            response = await asyncio.to_thread(
                client_openai.chat.completions.create,
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"}
            )
            content = response.choices[0].message.content.strip()
            data = json.loads(content)
        except Exception as e:
            print(f"OpenAI Quiz Generation Error: {e}")

    if data:
        # Unwrap if wrapped in a key
        if isinstance(data, dict):
            for key in ('questions', 'quiz', 'items'):
                if key in data and isinstance(data[key], list):
                    data = data[key]
                    break
            else:
                return []

        if len(data) > 10:
            data = data[:10]

        valid_questions = []
        for q in data:
            if 'question' in q and 'options' in q and 'answer' in q:
                if isinstance(q['options'], list) and len(q['options']) == 4:
                    valid_questions.append(q)

        if len(valid_questions) >= 1:
            return valid_questions

    return []


# Keep old name as alias so existing main.py calls still work
generate_quiz_gemini = generate_quiz
