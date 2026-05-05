import uuid

from django.conf import settings
from django.db import models


class Quiz(models.Model):
    title = models.CharField(max_length=256, null=True)
    creator = models.ForeignKey(settings.AUTH_USER_MODEL,
                                on_delete=models.SET_NULL, null=True,
                                related_name="quizzes")

    def __str__(self):
        if self.title == None:
            return "NONE"
        return self.title


class Answer_Choice(models.Model):
    question = models.ForeignKey("Quiz_Question", on_delete=models.CASCADE,
                                 related_name="choices")
    order = models.IntegerField()
    text = models.CharField(max_length=256)
    is_correct = models.BooleanField(default=False)

    class Meta:
        ordering = ("order", "id")

    def __str__(self):
        return f"Q{self.question.order} Choice {self.order}: {self.text}"


class Quiz_Question(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE,
                             related_name="questions")
    text = models.CharField(max_length=256)
    order = models.IntegerField()
    QUESTION_TYPES = (
        ("TF", "True or False"),
        ("MC", "Multiple Choice"),
        ("OE", "Short Answer"),
    )
    question_type = models.CharField(choices=QUESTION_TYPES,
                                     max_length=2, default="MC")
    # choices = models.ForeignKey(Answer_Choice,
    #                             on_delete=models.SET_NULL,
    #                             null=True, related_name="quiz_question")

    

    class Meta:
        ordering = ("order", "id")

    def __str__(self):
        return f"{self.quiz.title} - Q{self.order}"


def get_default_name():
    # TODO actual name generation logic
    return "USER"


class Quiz_Instance(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE,
                             related_name="instances")
    current_question = models.IntegerField()
    code = models.CharField(max_length=6)
    host = models.ForeignKey(settings.AUTH_USER_MODEL,
                             on_delete=models.CASCADE)
    game_id = models.UUIDField(primary_key=True, default=uuid.uuid4)

    def __str__(self):
        return f"{self.quiz.title} ({self.code})"


class Participant(models.Model):
    quiz_instance = models.ForeignKey(Quiz_Instance, on_delete=models.CASCADE,
                                      related_name="participants")
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    display_name = models.CharField(max_length=50, default=get_default_name)
    user = models.ForeignKey(settings.AUTH_USER_MODEL,
                             on_delete=models.SET_NULL, null=True)
    score = models.IntegerField(default=0)

    def __str__(self):
        return self.display_name


class AnswerSubmission(models.Model):
    participant = models.ForeignKey(Participant, on_delete=models.CASCADE,
                                    related_name="submissions")
    question = models.ForeignKey(Quiz_Question, on_delete=models.CASCADE,
                                 related_name="answer_choices")
    selected_answer = models.ForeignKey(Answer_Choice,
                                        on_delete=models.SET_NULL, null=True,
                                        related_name='+')
    is_correct = models.BooleanField(default=False)
    points_awarded = models.IntegerField(default=0)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-submitted_at",)

    def __str__(self):
        return f"{self.participant} - {self.question}"
