from django.contrib import admin
from .models import Employee, Attendance, Project, Fine, Bonus


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'position', 'salary', 'is_active', 'hire_date']
    list_filter  = ['position', 'is_active']
    search_fields = ['full_name', 'email']


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display  = ['employee', 'date', 'check_in', 'check_out', 'status', 'late_minutes']
    list_filter   = ['status', 'date']
    search_fields = ['employee__full_name']
    date_hierarchy = 'date'


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display  = ['name', 'responsible', 'deadline', 'progress', 'status', 'stage']
    list_filter   = ['status', 'stage']
    search_fields = ['name']


@admin.register(Fine)
class FineAdmin(admin.ModelAdmin):
    list_display  = ['employee', 'fine_type', 'amount', 'date', 'reason']
    list_filter   = ['fine_type', 'date']
    search_fields = ['employee__full_name']


@admin.register(Bonus)
class BonusAdmin(admin.ModelAdmin):
    list_display  = ['employee', 'amount', 'date', 'reason']
    search_fields = ['employee__full_name']
