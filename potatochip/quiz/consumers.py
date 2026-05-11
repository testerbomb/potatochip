from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
import asyncio

from .models import Participant, Quiz_Instance
"""
Consumer code debuged and refactored with the help of github copilot
"""


class LobbyConsumer(AsyncJsonWebsocketConsumer):
    # Shared per-quiz timer state for all consumer instances in this process.
    TIME_LIMITS = {}
    TIMER_TASKS = {}
    SUBMISSIONS = {}
    QUESTION_ENDED = {}
    QUESTION_REPORTS = {}
    PARTICIPANT_ANSWERS = {}

    async def connect(self):
        self.code = self.scope['url_route']['kwargs']['code']
        self.group_name = f'lobby_{self.code}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name,
        )

    async def receive_json(self, content):
        """Dispatch incoming websocket messages to dedicated handlers."""
        message_type = content.get('type')
        handlers = {
            'participant_join': self.handle_participant_join,
            'start-quiz': self.handle_start_quiz,
            'advance-question': self.handle_advance_question,
            'participant_resume': self.handle_participant_resume,
            'answer_submit': self.handle_answer_submit,
        }
        handler = handlers.get(message_type)
        if handler is None:
            return
        await handler(content)

    async def handle_participant_join(self, content):
        participant = await self.create_participant(content['screen_name'])
        await self.channel_layer.group_send(self.group_name, {
            'type': 'participant_joined',
            'screen_name': content['screen_name'],
            'participant_id': str(participant.id),
            'sender_channel_name': self.channel_name,
        })

    async def handle_start_quiz(self, content):
        del content
        self.initialize_quiz_state()
        quiz = await self.get_quiz()
        if not self.is_host_for_quiz(quiz):
            await self.send_error('Only the host can start the quiz.')
            return
        await self.advance_question()

    async def handle_advance_question(self, content):
        del content
        quiz = await self.get_quiz()
        if not self.is_host_for_quiz(quiz):
            await self.send_error('Only the host can advance the quiz.')
            return
        await self.advance_question()

    async def handle_participant_resume(self, content):
        quiz = await self.get_quiz()
        participant_id = content['participant_id']
        name = await self.get_participant_name(quiz, participant_id)
        particpant = await self.get_participant_by_id(participant_id)
        if name is None:
            await self.send_error('Participent does not exist!')
            return
        score = particpant.score
        question_order = quiz.current_question - 1
        question = None

        if question_order < 0:
            resume_state = 'waiting'
        elif self.has_question_ended(question_order):
            resume_state = 'submitted-grade'
        elif self.has_participant_answered(participant_id, question_order):
            resume_state = 'submitted'
        elif self.has_participant_submitted(participant_id, question_order):
            resume_state = 'submitted'
        else:
            question = await self.get_past_question_payload()
            resume_state = 'question'

        await self.send_json({
            'type': 'resume_success',
            'name': name,
            'participant_id': participant_id,
            'question': question,
            'score': score,
            'resume_state': resume_state,
            'correct': await self.has_participant_answered_correct(participant_id)
        })

    async def handle_answer_submit(self, content):
        quiz = await self.get_quiz()
        choices = await self.get_past_question_choices()
        correct, points, selected_index = self.grade_answer_submission(
            choices,
            content['answer_choice'],
        )

        participant = await self.get_participant_by_id(content['id'])
        if participant is not None:
            participant.score += points
            await database_sync_to_async(
                participant.save,
            )(update_fields=['score'])

            if selected_index is not None:
                await self.record_submission(
                    participant_id=str(content['id']),
                    selected_index=selected_index,
                )

        all_submitted = await self.mark_submission_and_check_all(
            content['id'],
        )
        if all_submitted:
            await self.end_question(quiz.current_question - 1)

        await self.get_time_limit_event().wait()
        await self.send_json({
            'type': 'answer_grade',
            'correct': correct,
            'points': points,
        })

    def initialize_quiz_state(self):
        self.SUBMISSIONS[self.code] = {}
        self.QUESTION_ENDED[self.code] = {}
        self.QUESTION_REPORTS[self.code] = {}
        self.PARTICIPANT_ANSWERS[self.code] = {}

    async def send_error(self, message):
        await self.send_json({
            'type': 'error',
            'message': message,
        })

    def is_host_for_quiz(self, quiz):
        user = self.scope.get('user')
        return bool(user and user.is_authenticated and user.id == quiz.host_id)

    def has_participant_answered(self, participant_id, question_order):
        answers_by_question = self.PARTICIPANT_ANSWERS.get(self.code, {})
        participant_answers = answers_by_question.get(question_order, {})
        return str(participant_id) in participant_answers

    def has_participant_submitted(self, participant_id, question_order):
        submissions_by_question = self.SUBMISSIONS.get(self.code, {})
        submitted_ids = submissions_by_question.get(question_order, set())
        return str(participant_id) in submitted_ids

    def has_question_ended(self, question_order):
        ended_by_question = self.QUESTION_ENDED.get(self.code, {})
        return bool(ended_by_question.get(question_order, False))

    def grade_answer_submission(self, choices, submitted_text):
        correct = False
        points = 0
        selected_index = None
        for idx, choice in enumerate(choices):
            if choice['text'] == submitted_text:
                selected_index = idx
                if choice['is_correct']:
                    correct = True
                    points = 100
                break
        return correct, points, selected_index

    def get_time_limit_event(self):
        event = self.TIME_LIMITS.get(self.code)
        if event is None:
            event = asyncio.Event()
            self.TIME_LIMITS[self.code] = event
        return event

    def cancel_timer_task(self):
        task = self.TIMER_TASKS.get(self.code)
        if task and not task.done():
            task.cancel()

    async def mark_submission_and_check_all(self, participant_id):
        quiz = await self.get_quiz()
        question_order = quiz.current_question - 1

        submissions_by_question = self.SUBMISSIONS.setdefault(self.code, {})
        submitted_ids = submissions_by_question.setdefault(
            question_order,
            set(),
        )
        submitted_ids.add(str(participant_id))

        participant_count = await self.get_participant_count()
        return (
            participant_count > 0
            and len(submitted_ids) >= participant_count
        )

    async def end_question(self, question_order):
        ended_by_question = self.QUESTION_ENDED.setdefault(self.code, {})
        if ended_by_question.get(question_order):
            return

        ended_by_question[question_order] = True
        self.get_time_limit_event().set()
        self.cancel_timer_task()
        report = self.get_question_report(question_order)
        await self.channel_layer.group_send(self.group_name, {
            'type': 'end_question_message',
            'question_order': question_order,
            'counts': report,
        })

    async def end_question_no_cancel(self, question_order):
        ended_by_question = self.QUESTION_ENDED.setdefault(self.code, {})
        if ended_by_question.get(question_order):
            return

        ended_by_question[question_order] = True
        self.get_time_limit_event().set()
        report = self.get_question_report(question_order)
        await self.channel_layer.group_send(self.group_name, {
            'type': 'end_question_message',
            'question_order': question_order,
            'counts': report,
        })

    async def record_submission(self, participant_id, selected_index):
        quiz = await self.get_quiz()
        question_order = quiz.current_question - 1

        reports_by_question = self.QUESTION_REPORTS.setdefault(self.code, {})
        report = reports_by_question.setdefault(question_order, [])

        answers_by_question = self.PARTICIPANT_ANSWERS.setdefault(
            self.code,
            {},
        )
        participant_answers = answers_by_question.setdefault(
            question_order,
            {},
        )

        previous_index = participant_answers.get(participant_id)
        if previous_index is not None and previous_index < len(report):
            report[previous_index] = max(0, report[previous_index] - 1)

        if selected_index >= len(report):
            return

        report[selected_index] += 1
        participant_answers[participant_id] = selected_index

    def get_question_report(self, question_order):
        reports_by_question = self.QUESTION_REPORTS.get(self.code, {})
        return reports_by_question.get(question_order, [])

    def clear_runtime_state(self):
        self.cancel_timer_task()
        self.TIME_LIMITS.pop(self.code, None)
        self.TIMER_TASKS.pop(self.code, None)
        self.SUBMISSIONS.pop(self.code, None)
        self.QUESTION_ENDED.pop(self.code, None)
        self.QUESTION_REPORTS.pop(self.code, None)
        self.PARTICIPANT_ANSWERS.pop(self.code, None)

    async def participant_joined(self, event):
        if event['sender_channel_name'] == self.channel_name:
            await self.send_json({
                'type': 'participant_joined',
                'participant_id': event['participant_id'],
                'screen_name': event['screen_name'],
            })
            return

        await self.send_json({
            'type': 'participant_joined',
            'screen_name': event['screen_name'],
        })

    async def quiz_started(self, event):
        await self.send_json({
            'type': 'quiz_started',
        })

    async def start_time_limit(self):
        try:
            await asyncio.sleep(30)
            quiz = await self.get_quiz()
            await self.end_question_no_cancel(quiz.current_question - 1)
        except asyncio.CancelledError:
            return
        except Exception as e:
            print(f"[start_time_limit] ERROR for {self.code}: {e}")

    async def advance_question(self):
        self.get_time_limit_event().clear()
        quiz = await self.get_quiz()
        question_order = quiz.current_question
        question = await self.get_current_question_payload()
        if question is None:
            # QUIZ IS DONE!
            leaderboard = await self.get_leaderboard()
            await self.channel_layer.group_send(self.group_name, {
                'type': 'quiz_complete_message',
                'leaderboard': leaderboard,
            })
            await self.delete_quiz_instance()
            self.clear_runtime_state()
            return

        # Reset submission tracking for this question.
        submissions_by_question = self.SUBMISSIONS.setdefault(self.code, {})
        submissions_by_question[question_order] = set()
        ended_by_question = self.QUESTION_ENDED.setdefault(self.code, {})
        ended_by_question[question_order] = False
        reports_by_question = self.QUESTION_REPORTS.setdefault(self.code, {})
        reports_by_question[question_order] = [
            0 for _ in question['choices']
        ]
        answers_by_question = self.PARTICIPANT_ANSWERS.setdefault(
            self.code,
            {},
        )
        answers_by_question[question_order] = {}

        await self.channel_layer.group_send(self.group_name, {
            'type': 'advance_question_message',
            'sender_channel_name': self.channel_name,
            'question': question,
            'time-limit': 30,
        })
        self.cancel_timer_task()
        self.TIMER_TASKS[self.code] = asyncio.create_task(
            self.start_time_limit(),
        )
        quiz.current_question += 1
        await database_sync_to_async(quiz.save)(
            update_fields=['current_question'],
        )

    async def advance_question_message(self, event):
        await self.send_json({
            'type': 'advance_question',
            'question': event['question'],
        })

    async def end_question_message(self, event):
        print("ending question")
        await self.send_json({
            'type': 'end_question',
            'question_order': event['question_order'],
            'counts': event.get('counts', []),
        })

    async def quiz_complete_message(self, event):
        await self.send_json({
            'type': 'quiz_complete',
            'leaderboard': event.get('leaderboard', []),
        })

    @database_sync_to_async
    def get_quiz(self):
        return Quiz_Instance.objects.get(code=self.code)

    @database_sync_to_async
    def get_current_question_payload(self):
        quiz_instance = Quiz_Instance.objects.select_related('quiz').get(
            code=self.code,
        )
        question = quiz_instance.quiz.questions.prefetch_related(
            'choices',
        ).filter(order=quiz_instance.current_question).first()
        if question is None:
            return None

        return {
            'id': question.id,
            'text': question.text,
            'order': question.order,
            'question_type': question.question_type,
            'choices': [
                {
                    'id': choice.id,
                    'order': choice.order,
                    'text': choice.text,
                }
                for choice in question.choices.all()
            ],
        }

    @database_sync_to_async
    def get_past_question_payload(self):
        quiz_instance = Quiz_Instance.objects.select_related('quiz').get(
            code=self.code,
        )

        # current_question points to the next unsent question after broadcast.
        question = quiz_instance.quiz.questions.prefetch_related(
            'choices',
        ).get(order=quiz_instance.current_question - 1)

        return {
            'id': question.id,
            'text': question.text,
            'order': question.order,
            'question_type': question.question_type,
            'choices': [
                {
                    'id': choice.id,
                    'order': choice.order,
                    'text': choice.text,
                }
                for choice in question.choices.all()
            ],
        }

    @database_sync_to_async
    def get_past_question_choices(self):
        """
        Get all answer choices from the current question.
        Server is always 1 question ahead, so current question is at
        current_question - 1.
        Returns a list of choice dicts with id, order, and text.
        """
        quiz_instance = Quiz_Instance.objects.select_related('quiz').get(
            code=self.code,
        )
        question = quiz_instance.quiz.questions.prefetch_related(
            'choices',
        ).get(order=quiz_instance.current_question - 1)

        return [
            {
                'text': choice.text,
                'is_correct': choice.is_correct,
            }
            for choice in question.choices.all()
        ]

    async def create_participant(self, screen_name):
        quiz_instance = await self.get_quiz()
        user = self.scope.get('user')
        return await self.create_participant_record(
            quiz_instance=quiz_instance,
            display_name=screen_name,
            user=user if user.is_authenticated else None,
        )

    @database_sync_to_async
    def create_participant_record(self, quiz_instance, display_name, user):
        return Participant.objects.create(
            quiz_instance=quiz_instance,
            display_name=display_name,
            user=user,
        )

    @database_sync_to_async
    def get_participant_by_id(self, participant_id):
        return Participant.objects.filter(id=participant_id).first()

    @database_sync_to_async
    def get_participant_name(self, quiz_instance, participant_id):
        participant = quiz_instance.participants.filter(
            id=participant_id,
        ).first()
        return participant.display_name if participant else None

    @database_sync_to_async
    def get_participant_count(self):
        quiz_instance = Quiz_Instance.objects.get(code=self.code)
        return quiz_instance.participants.count()

    @database_sync_to_async
    def get_leaderboard(self):
        quiz_instance = Quiz_Instance.objects.get(code=self.code)
        participants = quiz_instance.participants.order_by(
            '-score',
            'display_name',
        )
        return [
            {
                'name': participant.display_name,
                'score': participant.score,
                'id': str(participant.id),
            }
            for participant in participants
        ]

    async def has_participant_answered_correct(self, participant_id):
        """
        Check if a participant answered correctly for the current question.
        Returns True if the participant's selected answer is marked as correct, False otherwise.
        """
        quiz = await self.get_quiz()
        question_order = quiz.current_question - 1

        # Check if participant has answered this question
        if not self.has_participant_answered(participant_id, question_order):
            return False

        # Get the participant's selected index
        answers_by_question = self.PARTICIPANT_ANSWERS.get(self.code, {})
        participant_answers = answers_by_question.get(question_order, {})
        selected_index = participant_answers.get(str(participant_id))

        if selected_index is None:
            return False

        # Get the choices for this question
        choices = await self.get_question_choices_by_order(question_order)

        # Check if the selected choice is correct
        if selected_index >= len(choices):
            return False

        return choices[selected_index].get('is_correct', False)

    @database_sync_to_async
    def get_question_choices_by_order(self, question_order):
        """
        Get all answer choices for a question by its order.
        Returns a list of choice dicts with text and is_correct.
        """
        quiz_instance = Quiz_Instance.objects.select_related('quiz').get(
            code=self.code,
        )
        question = quiz_instance.quiz.questions.prefetch_related(
            'choices',
        ).get(order=question_order)

        return [
            {
                'text': choice.text,
                'is_correct': choice.is_correct,
            }
            for choice in question.choices.all()
        ]

    @database_sync_to_async
    def delete_quiz_instance(self):
        Quiz_Instance.objects.filter(code=self.code).delete()
