from django.urls import path

from . import views

urlpatterns = [
    path('', views.dashboard, name='job_hunt_dashboard'),
    path('create-hunt/', views.create_hunt, name='create_hunt'),
    path('create-posting/', views.create_posting, name='create_posting'),
    path('edit-posting/<int:posting_id>/', views.edit_posting, name='edit_posting'),
    path('toggle-hidden/<int:posting_id>/', views.toggle_posting_hidden, name='toggle_posting_hidden'),
    path('apply/<int:posting_id>/', views.create_application, name='create_application'),
    path('edit-application/<int:application_id>/', views.edit_application, name='edit_application'),
    path('create-event/', views.create_event, name='create_event'),
    path('event/<int:event_id>/update/', views.update_event, name='update_event'),
    path('generate-resume/', views.generate_resume, name='generate_resume'),
    path('resume-status/', views.resume_status, name='resume_status'),
    path('download-resume/', views.download_resume, name='download_resume'),
    path('posting/<int:posting_id>/generate-resume/', views.generate_posting_resume, name='generate_posting_resume'),
    path('posting/<int:posting_id>/resume-status/', views.posting_resume_status, name='posting_resume_status'),
    path('posting/<int:posting_id>/download-resume/', views.download_posting_resume, name='download_posting_resume'),
    path('posting/<int:posting_id>/resume-config/', views.resume_config, name='resume_config'),
    path('posting/<int:posting_id>/save-resume-config/', views.save_resume_config, name='save_resume_config'),
]
