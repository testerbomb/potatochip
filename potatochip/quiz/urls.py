from django.urls import path, include
from . import views
from . import api

urlpatterns = [
    path('', views.index, name='index'),
    path('home', views.home, name='home'),
    path('search', views.search, name='search'),
    path('create/<int:pk>', views.create, name='create'),
    path('join/', views.join, name="join"),
    path('join/<str:code>/', views.join_quiz, name="join_quiz"),
    path('host/<str:code>/', views.host_lobby, name='host_lobby'),
    path('quiz/<int:pk>/', views.QuizDetailView.as_view(), name='quiz_detail'),
    path('accounts/', include('django.contrib.auth.urls')),
    path('accounts/signup/', views.register, name='register'),
    path('api/', api.api.urls),
    path('about/', views.about, name='about'),
]
