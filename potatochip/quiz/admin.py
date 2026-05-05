from django.contrib import admin

from .models import (
    AnswerSubmission,
    Answer_Choice,
    Participant,
    Quiz,
    Quiz_Instance,
    Quiz_Question,
)


class HiddenFromIndexAdmin(admin.ModelAdmin):
    def get_model_perms(self, request):
        return {}


class QuestionAnswerInline(admin.TabularInline):
    model = Answer_Choice
    show_change_link = True
    extra = 1


class QuizQuestionInline(admin.TabularInline):
    model = Quiz_Question
    show_change_link = True
    extra = 0


class ParticipantInline(admin.TabularInline):
    model = Participant
    show_change_link = True
    extra = 0


class AnswerSubmissionInline(admin.TabularInline):
    model = AnswerSubmission
    show_change_link = True
    extra = 0
    readonly_fields = ("submitted_at",)


class QuizInstanceInline(admin.TabularInline):
    model = Quiz_Instance
    show_change_link = True
    extra = 0
    readonly_fields = ("game_id",)


class QuizQuestionAdmin(HiddenFromIndexAdmin):
    inlines = [QuestionAnswerInline]


class QuizAdmin(admin.ModelAdmin):
    inlines = [QuizQuestionInline, QuizInstanceInline]


class QuizInstanceAdmin(HiddenFromIndexAdmin):
    inlines = [ParticipantInline]


class AnswerChoiceAdmin(HiddenFromIndexAdmin):
    pass


class ParticipantAdmin(HiddenFromIndexAdmin):
    inlines = [AnswerSubmissionInline]


class AnswerSubmissionAdmin(HiddenFromIndexAdmin):
    pass


# Register your models here.
admin.site.register(Quiz, QuizAdmin)
admin.site.register(Quiz_Question, QuizQuestionAdmin)
admin.site.register(Quiz_Instance, QuizInstanceAdmin)
admin.site.register(Answer_Choice, AnswerChoiceAdmin)
admin.site.register(Participant, ParticipantAdmin)
admin.site.register(AnswerSubmission, AnswerSubmissionAdmin)
