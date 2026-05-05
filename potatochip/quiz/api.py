from ninja import NinjaAPI, Schema
from ninja.errors import HttpError
from .models import Quiz, Quiz_Instance, Quiz_Question, Answer_Choice
from django.shortcuts import get_object_or_404
from django.db.models import Q
import random

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
    for index, question in enumerate(quiz.questions.all(), start=1):
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
    return {'code': instance.code}


@api.post('/create/')
def create_new_quiz(request):
    quiz = Quiz.objects.create(
         creator=request.user
     )
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
    return {'success': True}

@api.patch('/quiz/{quiz_id}/')
def update_quiz_title(request, quiz_id: int, payload: QuizTitleSchema):
    quiz = get_object_or_404(Quiz, pk=quiz_id)
    _assert_quiz_owner(quiz, request.user)
    quiz.title = payload.title
    quiz.save()
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


def generate_code():
    # TODO we might need to change this
    while True:
        code = ''.join([str(random.randint(0, 9)) for _ in range(6)])
        if not Quiz_Instance.objects.filter(code=code).exists():
            return code
