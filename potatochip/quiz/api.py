from ninja import NinjaAPI, Schema
from typing import List
from ninja.errors import HttpError
from .models import Quiz, Quiz_Instance, Quiz_Question, Answer_Choice
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.conf import settings
import random
import json
import requests
import logging

logger = logging.getLogger('api') # get an instance of a logger

api = NinjaAPI()

class QuizTitleSchema(Schema):
    title: str

class QuestionSchema(Schema):
    text: str
    order: int
    question_type: str = "MC"

class ChoiceSchema(Schema):
    text: str
    order: int
    is_correct: bool = False

class BulkDeleteSchema(Schema):
    ids: List[int]

class GenerateSchema(Schema):
    topic: str
    num_questions: int = 5


def _assert_quiz_owner(quiz, user):
    if quiz.creator != user:
        raise HttpError(403, "You don't own this quiz.")


def _serialize_choice(choice):
    return {
        'id': choice.id,
        'text': choice.text,
        'order': choice.order,
        'is_correct': choice.is_correct,
    }


def _serialize_question(question):
    return {
        'id': question.id,
        'text': question.text,
        'order': question.order,
        'question_type': question.question_type,
        'choices': [_serialize_choice(choice) for choice in question.choices.all()],
    }


def _reorder_questions(quiz):
    for index, question in enumerate(quiz.questions.all(), start=0):
        if question.order != index:
            question.order = index
            question.save(update_fields=['order'])


def _reorder_choices(question):
    for index, choice in enumerate(question.choices.all(), start=1):
        if choice.order != index:
            choice.order = index
            choice.save(update_fields=['order'])


@api.post('/host/{quiz_id}/')
def create_instance(request, quiz_id: int):
    quiz = get_object_or_404(Quiz, pk=quiz_id)
    instance = Quiz_Instance.objects.create(
        quiz=quiz,
        host=request.user,
        current_question=0,
        code=generate_code(),
    )
    logger.info(f"User {request.user} started hosting Quiz {quiz_id} (Code: {instance.code})")
    return {'code': instance.code}


@api.post('/create/')
def create_new_quiz(request):
    quiz = Quiz.objects.create(
        creator=request.user
    )
    logger.info(f"User {request.user} created new Quiz {quiz.id}")
    return {'id': quiz.id}


@api.get('/quiz/')
def search(request, q: str = ''):
    quizzes = Quiz.objects.all()
    if q:
        quizzes = quizzes.filter(
            Q(title__icontains=q) | Q(questions__text__icontains=q)
        ).distinct()
    return {
        'results': [
            {'id': quiz.id, 'title': quiz.title or 'None'}
            for quiz in quizzes
        ]
    }


@api.get('/quiz/{quiz_id}/')
def get_quiz_for_edit(request, quiz_id: int):
    quiz = get_object_or_404(Quiz, pk=quiz_id)
    _assert_quiz_owner(quiz, request.user)
    return {
        'id': quiz.id,
        'title': quiz.title or '',
        'questions': [_serialize_question(question) for question in quiz.questions.all()],
    }


@api.delete('/quiz/{quiz_id}/')
def delete_quiz(request, quiz_id: int):
    quiz = get_object_or_404(Quiz, pk=quiz_id)
    _assert_quiz_owner(quiz, request.user)
    quiz.delete()
    logger.info(f"User {request.user} deleted Quiz {quiz_id}")
    return {'success': True}


@api.patch('/quiz/{quiz_id}/')
def update_quiz_title(request, quiz_id: int, payload: QuizTitleSchema):
    quiz = get_object_or_404(Quiz, pk=quiz_id)
    _assert_quiz_owner(quiz, request.user)
    quiz.title = payload.title
    quiz.save()
    logger.info(f"User {request.user} renamed Quiz {quiz_id} to '{payload.title}'")
    return {'id': quiz.id, 'title': quiz.title}


@api.post('/quiz/{quiz_id}/questions/')
def add_question(request, quiz_id: int, payload: QuestionSchema):
    quiz = get_object_or_404(Quiz, pk=quiz_id)
    _assert_quiz_owner(quiz, request.user)
    question = Quiz_Question.objects.create(
        quiz=quiz,
        text=payload.text,
        order=payload.order,
        question_type=payload.question_type,
    )
    logger.info(f"User {request.user} added question to Quiz {quiz_id}: '{payload.text[:30]}...'")
    return {'id': question.id, 'text': question.text, 'order': question.order}


@api.patch('/questions/{question_id}/')
def update_question(request, question_id: int, payload: QuestionSchema):
    question = get_object_or_404(Quiz_Question, pk=question_id)
    _assert_quiz_owner(question.quiz, request.user)
    question.text = payload.text
    question.order = payload.order
    question.question_type = payload.question_type
    question.save()
    return {'id': question.id, 'text': question.text, 'order': question.order}


@api.delete('/questions/{question_id}/')
def delete_question(request, question_id: int):
    question = get_object_or_404(Quiz_Question, pk=question_id)
    quiz = question.quiz
    _assert_quiz_owner(quiz, request.user)
    question.delete()
    _reorder_questions(quiz)
    return {'success': True}


@api.post('/questions/{question_id}/choices/')
def add_choice(request, question_id: int, payload: ChoiceSchema):
    question = get_object_or_404(Quiz_Question, pk=question_id)
    _assert_quiz_owner(question.quiz, request.user)
    choice = Answer_Choice.objects.create(
        question=question,
        text=payload.text,
        order=payload.order,
        is_correct=payload.is_correct,
    )
    logger.info(f"User {request.user} added choice to Question {question_id}")
    return {
        'id': choice.id,
        'text': choice.text,
        'order': choice.order,
        'is_correct': choice.is_correct,
    }


@api.patch('/choices/{choice_id}/')
def update_choice(request, choice_id: int, payload: ChoiceSchema):
    choice = get_object_or_404(Answer_Choice, pk=choice_id)
    _assert_quiz_owner(choice.question.quiz, request.user)
    choice.text = payload.text
    choice.order = payload.order
    choice.is_correct = payload.is_correct
    choice.save()
    return {
        'id': choice.id,
        'text': choice.text,
        'order': choice.order,
        'is_correct': choice.is_correct,
    }


@api.delete('/choices/{choice_id}/')
def delete_choice(request, choice_id: int):
    choice = get_object_or_404(Answer_Choice, pk=choice_id)
    question = choice.question
    _assert_quiz_owner(question.quiz, request.user)
    choice.delete()
    _reorder_choices(question)
    return {'success': True}


@api.post('/quiz/{quiz_id}/generate/')
def generate_questions(request, quiz_id: int, payload: GenerateSchema):
    logger.info(f"User {request.user} initiated generation for Quiz {quiz_id} on topic: {payload.topic}")
    
    quiz = get_object_or_404(Quiz, pk=quiz_id)
    _assert_quiz_owner(quiz, request.user)

    api_key = settings.GEMINI_API_KEY
    num_q = max(1, min(payload.num_questions, 10))
    
    # 1. We force JSON via the prompt since the config field is failing
    prompt = (
        f'Generate {num_q} multiple choice quiz questions about "{payload.topic}". '
        f'Respond with a JSON array. Each element must have these fields: '
        f'"text" (string), "choices" (array of 4 strings), "correct_index" (int). '
        f'Do not include markdown formatting like ```json.'
    )

    # Gemini 2.5, 250 prompts for per-day
    url = f'https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={api_key}'
    
    payload_data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.7}
    }

    # 2. Call Gemini
    response = requests.post(url, json=payload_data, timeout=30)
    
    # if prompt limit is hit switch to the lite version for more
    if response.status_code == 429:
        logger.warning(f"User {request.user} hit Gemini's pro tier Rate Limit.")
        # Switch to Gemini 2.5 lite, 1,500 prompts for per-day
        url = f'https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash-lite:generateContent?key={api_key}'
        response = requests.post(url, json=payload_data, timeout=30)

        if response.status_code == 429:
            logger.warning(f"User {request.user} hit of Gemini's Rate Limit for all tiers.")
            raise HttpError(429, "Too many AI requests. Please wait a minute before retrying.")

    if response.status_code != 200:
        logger.error(f"Gemini API Error {response.status_code}: {response.text}")
        raise HttpError(502, "The AI service is having trouble right now.")

    result = response.json()
    raw_text = result['candidates'][0]['content']['parts'][0]['text'].strip()

    # 3. Robust JSON Parsing
    # Sometimes Gemini still adds ```json ... ``` blocks even if asked not to
    if raw_text.startswith("```"):
        raw_text = "\n".join(raw_text.splitlines()[1:-1])
    
    try:
        questions_data = json.loads(raw_text)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse AI JSON. Raw text: {raw_text}")
        raise HttpError(502, "AI returned invalid data format.")

    # 4. randomize because Gemini makes them only b and c answers
    for item in questions_data:
        choices = item['choices']
        correct_answer = choices[item['correct_index']]
        
        # shuffle the list in place
        random.shuffle(choices)
        
        # find the new index of the correct answer
        new_index = choices.index(correct_answer)
        # update correct answer
        item['correct_index'] = new_index

    # 5. Save to Database (Keeping your existing logic)
    if not quiz.title:
        quiz.title = payload.topic
        quiz.save()
        logger.info(f"Updated quiz title to: {quiz.title}")

    start_order = quiz.questions.count()
    created_questions = []

    for i, q_data in enumerate(questions_data):
        question = Quiz_Question.objects.create(
            quiz=quiz,
            text=q_data['text'],
            order=start_order + i,
            question_type='MC',
        )
        for j, choice_text in enumerate(q_data['choices']):
            Answer_Choice.objects.create(
                question=question,
                text=choice_text,
                order=j + 1,
                is_correct=(j == q_data['correct_index']),
            )
        created_questions.append(_serialize_question(question))

    logger.info(f"Successfully generated and saved {len(created_questions)} questions for Quiz {quiz_id}")
    return {'questions': created_questions, 'title': quiz.title}


def generate_code():
    while True:
        code = ''.join([str(random.randint(0, 9)) for _ in range(6)])
        if not Quiz_Instance.objects.filter(code=code).exists():
            return code


@api.post('/delete-quiz/')
def bulk_delete_quizzes(request, payload: BulkDeleteSchema):
    results = []
    for pk in payload.ids:
        try:
            quiz = Quiz.objects.get(pk=pk)
        except Quiz.DoesNotExist:
            results.append({'id': pk, 'success': False, 'error': 'not found'})
            continue

        if quiz.creator != request.user:
            results.append({'id': pk, 'success': False, 'error': "not owner"})
            continue

        quiz.delete()
        results.append({'id': pk, 'success': True})
        logger.info(f"User {request.user} bulk-deleted Quiz {pk}")

    return {'results': results}