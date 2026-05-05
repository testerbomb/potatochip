"""
ASGI config for potatochip project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'potatochip.settings')

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

from django.conf import settings
from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler
from django.core.asgi import get_asgi_application

http_application = get_asgi_application()

# Daphne does not serve static files by default, so wrap the HTTP app
# with Django's static files handler for local development and previews.
http_application = ASGIStaticFilesHandler(http_application)

import quiz.routing

application = ProtocolTypeRouter({
    "http": http_application,
    "websocket": AuthMiddlewareStack(
        URLRouter(quiz.routing.websocket_urlpatterns)
    ),
})
