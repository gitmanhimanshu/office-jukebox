"""URL routes for the music app."""

from django.urls import path
from . import views

urlpatterns = [
    # Pages
    path("", views.welcome_view, name="welcome"),
    path("create-room/", views.create_room_view, name="create_room"),
    path("leave-room/", views.leave_room_view, name="leave_room"),
    path("change-name/", views.change_name_view, name="change_name"),
    path("room/<str:room_code>/", views.dashboard_view, name="dashboard"),
    path("room/<str:room_code>/player/", views.player_view, name="player"),
    path("room/<str:room_code>/moderator/", views.moderator_view, name="moderator"),

    # REST / JSON APIs
    path("api/rooms/<str:room_code>/state/", views.api_room_state, name="api_room_state"),
    path("api/youtube/search/", views.api_youtube_search, name="api_youtube_search"),
    path("api/rooms/<str:room_code>/queue/add/", views.api_queue_add, name="api_queue_add"),
    path("api/rooms/<str:room_code>/queue/<uuid:item_id>/vote/", views.api_queue_vote, name="api_queue_vote"),
    path("api/rooms/<str:room_code>/queue/<uuid:item_id>/remove/", views.api_queue_remove, name="api_queue_remove"),
    path("api/rooms/<str:room_code>/player/heartbeat/", views.api_player_heartbeat, name="api_player_heartbeat"),
    path("api/rooms/<str:room_code>/player/next/", views.api_player_next, name="api_player_next"),
    path("api/rooms/<str:room_code>/player/skip/", views.api_player_skip, name="api_player_skip"),
]
