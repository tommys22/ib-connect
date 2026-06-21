"""URL routes for the core app."""

from django.urls import path

from . import views

urlpatterns = [
    # Directory
    path("", views.alumni_list, name="alumni_list"),
    path("alumni/add/", views.alumni_add, name="alumni_add"),
    path("alumni/<int:pk>/", views.alumni_detail, name="alumni_detail"),
    path("alumni/<int:pk>/verify/", views.alumni_verify, name="alumni_verify"),
    path("alumni/<int:pk>/suggest-edit/", views.alumni_suggest_edit, name="alumni_suggest_edit"),
    path("alumni/<int:pk>/report/", views.alumni_report, name="alumni_report"),
    path("alumni/<int:pk>/restore/", views.alumni_restore, name="alumni_restore"),
    # Admin review queue (maintainer only)
    path("review/", views.review_queue, name="review_queue"),
    path("review/edit/<int:edit_id>/<str:action>/", views.review_edit, name="review_edit"),
    path("review/flag/<int:flag_id>/<str:action>/", views.review_flag, name="review_flag"),
    # Student profile / contributions
    path("profile/", views.profile, name="profile"),
    # Auth (login/logout come from django.contrib.auth.urls, wired in config/urls.py)
    path("signup/", views.signup, name="signup"),
]
