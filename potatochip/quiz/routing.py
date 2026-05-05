from django.urls import path
from . import consumers

websocket_urlpatterns = [
    path('ws/lobby/<str:code>/', consumers.LobbyConsumer.as_asgi()),
]
