from django.urls import path
from . import views

urlpatterns = [
    path('', views.overview, name='overview'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('attendance/', views.attendance_view, name='attendance'),
    path('checkin/', views.checkin, name='checkin'),
    path('projects/', views.projects_view, name='projects'),
    path('fines/', views.fines_view, name='fines'),
    path('reports/', views.reports_view, name='reports'),
    path('employee/<int:pk>/', views.employee_detail, name='employee_detail'),
    path('employees/', views.employees_view, name='employees'),
    path('api/fine-amount/', views.get_fine_amount_api, name='fine_amount_api'),
]
