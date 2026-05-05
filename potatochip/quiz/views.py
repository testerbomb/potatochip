from django.shortcuts import render, redirect
from django.http import Http404
from django.urls import reverse
from django.views.generic import DetailView
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from .models import Quiz, Quiz_Instance
from django.shortcuts import get_object_or_404
from django.core.paginator import Paginator


# Create your views here.
def index(request):
    return redirect("home")


@login_required
def home(request):
    quizzes = Quiz.objects.filter(creator=request.user)
    paginator = Paginator(quizzes, 15)  # 15 items per page + plus button (4 rows x 4 columns)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, "home.html", {"page_obj": page_obj})

@login_required
def create(request, pk):
    quiz = get_object_or_404(Quiz, id=pk, creator=request.user)
    return render(request, "create.html", {"quiz": quiz, "quiz_id": quiz.id})

def search(request):
    return render(request, 'search.html')

@login_required
def host_lobby(request, code):
    try:
        instance = Quiz_Instance.objects.get(code=code)
    except Quiz_Instance.DoesNotExist:
        raise Http404
    if request.user != instance.host:
        return redirect('/')
    join_url = request.build_absolute_uri(reverse('join_quiz', args=[code]))
    return render(request, 'host_lobby.html', {'instance': instance, 'join_url': join_url})


class QuizDetailView(DetailView):
    model = Quiz
    template_name = 'quiz.html'
    context_object_name = 'quiz'


def join_quiz(request, code):
    try:
        instance = Quiz_Instance.objects.get(code=code)
    except Quiz_Instance.DoesNotExist:
        raise Http404
    return render(request, 'lobby.html', {'instance': instance})


def join(request):
    return render(request, "join.html")


def register(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('home')
    else:
        form = UserCreationForm()
    return render(request, 'registration/register.html', {'form': form})

def about(request):
    return render(request, "about.html")


def default_not_found(request, exception):
    if request.path.startswith('/join/') or request.path.startswith('/host/'):
        return render(request, "quiz_404.html", status=404)
    return render(request, "404.html", status=404)
