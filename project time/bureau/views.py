import json
import base64
import datetime
import os
import requests

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db.models import Sum, Count, Avg
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User

from .models import Employee, Attendance, Project, Fine, Bonus

def admin_only(view_func):
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_superuser:
            try:
                profile = request.user.employee_profile
                return redirect('employee_detail', pk=profile.id)
            except Employee.DoesNotExist:
                return redirect('logout')
        return view_func(request, *args, **kwargs)
    return _wrapped_view



# ─── Auth ────────────────────────────────────────────────────────────────────

def login_view(request):
    if request.user.is_authenticated:
        return redirect('overview')
    error = None
    if request.method == 'POST':
        username = request.POST.get('username', '')
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect(request.GET.get('next', 'overview'))
        else:
            error = 'Неверный логин или пароль'
    return render(request, 'bureau/login.html', {'error': error})


def logout_view(request):
    logout(request)
    return redirect('login')


# ─── Helpers ────────────────────────────────────────────────────────────────

def send_telegram_notification(employee, status, photo_path=None):
    token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
    chat_id = getattr(settings, 'TELEGRAM_ADMIN_CHAT_ID', '')
    if not token or not chat_id:
        return
    now = timezone.localtime(timezone.now()).strftime('%H:%M')
    if status == 'late':
        text = f"⚠️ ОПОЗДАНИЕ\n👤 {employee.full_name}\n💼 {employee.get_position_display()}\n🕐 {now}"
    else:
        text = f"✅ ПРИШЁЛ\n👤 {employee.full_name}\n💼 {employee.get_position_display()}\n🕐 {now}"
    try:
        if photo_path and os.path.exists(photo_path):
            with open(photo_path, 'rb') as photo:
                requests.post(
                    f'https://api.telegram.org/bot{token}/sendPhoto',
                    data={'chat_id': chat_id, 'caption': text},
                    files={'photo': photo},
                    timeout=5
                )
        else:
            requests.post(
                f'https://api.telegram.org/bot{token}/sendMessage',
                data={'chat_id': chat_id, 'text': text},
                timeout=5
            )
    except Exception:
        pass


# ─── Overview ────────────────────────────────────────────────────────────────

@login_required
@admin_only
def overview(request):
    today = datetime.date.today()
    now = timezone.now()
    year, month = now.year, now.month

    employees = Employee.objects.filter(is_active=True)
    total_employees = employees.count()

    today_attendances = Attendance.objects.filter(date=today).select_related('employee')
    present_today = today_attendances.filter(status__in=['present', 'late', 'left']).count()

    active_projects = Project.objects.filter(status='in_progress').count()
    deadlines_this_week = Project.objects.filter(
        deadline__gte=today,
        deadline__lte=today + datetime.timedelta(days=7),
        status__in=['in_progress', 'review']
    ).count()

    monthly_fines = Fine.objects.filter(
        date__year=year, date__month=month
    ).aggregate(total=Sum('amount'))['total'] or 0

    attendance_list = []
    for emp in employees:
        att = today_attendances.filter(employee=emp).first()
        attendance_list.append({'employee': emp, 'attendance': att})

    sidebar_projects = Project.objects.filter(status__in=['in_progress', 'review'])[:5]

    context = {
        'total_employees': total_employees,
        'present_today': present_today,
        'active_projects': active_projects,
        'deadlines_this_week': deadlines_this_week,
        'monthly_fines': monthly_fines,
        'today_date': today,
        'attendance_list': attendance_list,
        'sidebar_projects': sidebar_projects,
        'tab': 'overview',
    }
    return render(request, 'bureau/overview.html', context)


# ─── Employee Detail ─────────────────────────────────────────────────────────

@login_required
def employee_detail(request, pk):
    if not request.user.is_superuser:
        try:
            profile = request.user.employee_profile
            if str(profile.id) != str(pk):
                return redirect('employee_detail', pk=profile.id)
        except Employee.DoesNotExist:
            return redirect('logout')
            
    employee = get_object_or_404(Employee, pk=pk)
    now = timezone.now()
    year = int(request.GET.get('year', now.year))
    month = int(request.GET.get('month', now.month))

    months_ru = ['', 'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
                 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']

    # Attendance records for selected month
    attendances = Attendance.objects.filter(
        employee=employee, date__year=year, date__month=month
    ).order_by('-date')

    days_worked = attendances.exclude(status='absent').count()
    lates = attendances.filter(status='late').count()
    hours_worked = sum(a.get_hours_worked() for a in attendances)

    # Fines
    fines = Fine.objects.filter(
        employee=employee, date__year=year, date__month=month
    ).order_by('-date')
    fines_total = fines.aggregate(total=Sum('amount'))['total'] or 0

    # Bonus
    bonuses = Bonus.objects.filter(
        employee=employee, date__year=year, date__month=month
    ).order_by('-date')
    bonus_total = bonuses.aggregate(total=Sum('amount'))['total'] or 0

    net_salary = employee.salary - fines_total + bonus_total

    # Projects (all time, as responsible)
    projects = Project.objects.filter(responsible=employee).order_by('-updated_at')

    # Total attendance all time
    total_days_all = Attendance.objects.filter(employee=employee).exclude(status='absent').count()

    # Avg check_in for this month
    month_checkins = attendances.filter(check_in__isnull=False)
    avg_checkin = None
    if month_checkins.exists():
        total_seconds = sum(
            a.check_in.hour * 3600 + a.check_in.minute * 60 + a.check_in.second
            for a in month_checkins
        )
        avg_s = total_seconds // month_checkins.count()
        avg_checkin = f"{avg_s // 3600:02d}:{(avg_s % 3600) // 60:02d}"

    # Attendance % this month (assume 22 working days)
    working_days_in_month = 22
    attendance_pct = round((days_worked / working_days_in_month) * 100) if working_days_in_month > 0 else 0
    attendance_pct = min(attendance_pct, 100)

    # Hours % (assume 176 hours/month = 22 days * 8 hours)
    hours_pct = round((hours_worked / 176) * 100) if hours_worked > 0 else 0
    hours_pct = min(hours_pct, 100)

    context = {
        'employee': employee,
        'attendances': attendances,
        'days_worked': days_worked,
        'hours_worked': round(hours_worked, 1),
        'lates': lates,
        'fines': fines,
        'fines_total': fines_total,
        'bonuses': bonuses,
        'bonus_total': bonus_total,
        'net_salary': net_salary,
        'projects': projects,
        'total_days_all': total_days_all,
        'avg_checkin': avg_checkin,
        'attendance_pct': attendance_pct,
        'hours_pct': hours_pct,
        'year': year,
        'month': month,
        'month_name': months_ru[month],
        'tab': 'attendance',
    }
    return render(request, 'bureau/employee_detail.html', context)


# ─── Attendance ──────────────────────────────────────────────────────────────

@login_required
@admin_only
def attendance_view(request):
    today = datetime.date.today()
    employees = Employee.objects.filter(is_active=True)

    today_records = Attendance.objects.filter(date=today).select_related('employee')
    attendance_map = {r.employee_id: r for r in today_records}

    display_list = []
    for emp in employees:
        att = attendance_map.get(emp.id)
        display_list.append({'employee': emp, 'attendance': att})

    context = {
        'employees': employees,
        'display_list': display_list,
        'today_date': today,
        'tab': 'attendance',
    }
    return render(request, 'bureau/attendance.html', context)


@csrf_exempt
@login_required
def checkin(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    employee_id = request.POST.get('employee_id')
    action = request.POST.get('action', 'checkin')
    photo_data = request.POST.get('photo')

    if not employee_id:
        return JsonResponse({'error': 'Не указан сотрудник'}, status=400)

    employee = get_object_or_404(Employee, id=employee_id)
    today = datetime.date.today()
    now_local = timezone.localtime(timezone.now())
    current_time = now_local.time()

    att, created = Attendance.objects.get_or_create(
        employee=employee,
        date=today,
        defaults={'status': 'absent'}
    )

    photo_path = None
    if photo_data and action == 'checkin':
        try:
            header, encoded = photo_data.split(',', 1)
            img_data = base64.b64decode(encoded)
            photo_dir = os.path.join(settings.MEDIA_ROOT, 'attendance_photos')
            os.makedirs(photo_dir, exist_ok=True)
            filename = f"{employee.id}_{today.strftime('%Y%m%d')}.jpg"
            photo_path = os.path.join(photo_dir, filename)
            with open(photo_path, 'wb') as f:
                f.write(img_data)
            att.check_in_photo = f"attendance_photos/{filename}"
        except Exception:
            pass

    if action == 'checkin' and not att.check_in:
        att.check_in = current_time
        att.save()

        work_start = datetime.time(settings.WORK_START_HOUR, settings.WORK_START_MINUTE)
        fine_created = None
        if current_time > work_start:
            late_minutes = att.late_minutes
            if late_minutes <= 30:
                fine_type = 'late_under_30'
                fine_amount = 2500
            else:
                fine_type = 'late_over_30'
                fine_amount = 5000
            fine_created = Fine.objects.create(
                employee=employee,
                fine_type=fine_type,
                amount=fine_amount,
                date=today,
                reason=f"Опоздание на {late_minutes} мин",
                attendance=att
            )

        send_telegram_notification(employee, att.status, photo_path)

        return JsonResponse({
            'success': True,
            'message': f"{employee.full_name} пришёл в {current_time.strftime('%H:%M')}",
            'status': att.status,
            'status_display': att.get_status_display(),
            'check_in': current_time.strftime('%H:%M'),
            'late_minutes': att.late_minutes,
            'fine': float(fine_created.amount) if fine_created else None,
        })

    elif action == 'checkout' and att.check_in and not att.check_out:
        att.check_out = current_time
        att.status = 'left'
        att.save()

        return JsonResponse({
            'success': True,
            'message': f"{employee.full_name} ушёл в {current_time.strftime('%H:%M')}",
            'status': 'left',
            'status_display': 'Ушёл',
            'check_out': current_time.strftime('%H:%M'),
            'hours_worked': att.get_hours_worked(),
        })
    else:
        return JsonResponse({
            'success': False,
            'message': 'Уже отмечено'
        })


# ─── Projects ─────────────────────────────────────────────────────────────────

@login_required
@admin_only
def projects_view(request):
    projects = Project.objects.select_related('responsible').all()
    employees = Employee.objects.filter(is_active=True)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create':
            name = request.POST.get('name')
            description = request.POST.get('description', '')
            responsible_id = request.POST.get('responsible')
            deadline = request.POST.get('deadline')
            stage = request.POST.get('stage', 'sketch')
            progress = int(request.POST.get('progress', 0))

            Project.objects.create(
                name=name,
                description=description,
                responsible_id=responsible_id if responsible_id else None,
                deadline=deadline,
                stage=stage,
                progress=progress,
            )
            messages.success(request, 'Проект создан!')
        elif action == 'update':
            proj_id = request.POST.get('project_id')
            proj = get_object_or_404(Project, id=proj_id)
            proj.progress = int(request.POST.get('progress', proj.progress))
            proj.status = request.POST.get('status', proj.status)
            proj.stage = request.POST.get('stage', proj.stage)
            proj.save()
            messages.success(request, 'Проект обновлён!')
        elif action == 'delete':
            proj_id = request.POST.get('project_id')
            Project.objects.filter(id=proj_id).delete()
            messages.success(request, 'Проект удалён!')
        return redirect('projects')

    context = {
        'projects': projects,
        'employees': employees,
        'tab': 'projects',
    }
    return render(request, 'bureau/projects.html', context)


# ─── Fines ───────────────────────────────────────────────────────────────────

@login_required
@admin_only
def fines_view(request):
    now = timezone.now()
    year = int(request.GET.get('year', now.year))
    month = int(request.GET.get('month', now.month))

    fines = Fine.objects.filter(
        date__year=year, date__month=month
    ).select_related('employee').order_by('-date')

    total_fines = fines.aggregate(total=Sum('amount'))['total'] or 0
    employees = Employee.objects.filter(is_active=True)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add':
            employee_id = request.POST.get('employee')
            fine_type = request.POST.get('fine_type')
            amount = request.POST.get('amount')
            date = request.POST.get('date')
            reason = request.POST.get('reason', '')

            if not amount and fine_type in Fine.FINE_AMOUNTS:
                amount = Fine.FINE_AMOUNTS[fine_type]

            Fine.objects.create(
                employee_id=employee_id,
                fine_type=fine_type,
                amount=amount,
                date=date or datetime.date.today(),
                reason=reason
            )
            messages.success(request, 'Штраф добавлен!')
        elif action == 'delete':
            fine_id = request.POST.get('fine_id')
            Fine.objects.filter(id=fine_id).delete()
            messages.success(request, 'Штраф удалён!')
        return redirect(f'/fines/?year={year}&month={month}')

    months_ru = ['', 'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
                 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']

    context = {
        'fines': fines,
        'total_fines': total_fines,
        'employees': employees,
        'fine_types': Fine.FINE_TYPE_CHOICES,
        'fine_amounts': Fine.FINE_AMOUNTS,
        'year': year,
        'month': month,
        'month_name': months_ru[month],
        'tab': 'fines',
    }
    return render(request, 'bureau/fines.html', context)


# ─── Reports ─────────────────────────────────────────────────────────────────

@login_required
@admin_only
def reports_view(request):
    now = timezone.now()
    year = int(request.GET.get('year', now.year))
    month = int(request.GET.get('month', now.month))

    employees = Employee.objects.filter(is_active=True)

    months_ru = ['', 'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
                 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']

    employee_stats = []
    total_hours_all = 0
    total_lates_all = 0
    total_fines_all = 0

    for emp in employees:
        attendances = Attendance.objects.filter(
            employee=emp, date__year=year, date__month=month
        )
        days_worked = attendances.exclude(status='absent').count()
        lates = attendances.filter(status='late').count()

        hours = 0
        for att in attendances:
            hours += att.get_hours_worked()

        fines_total = Fine.objects.filter(
            employee=emp, date__year=year, date__month=month
        ).aggregate(total=Sum('amount'))['total'] or 0

        bonus_total = Bonus.objects.filter(
            employee=emp, date__year=year, date__month=month
        ).aggregate(total=Sum('amount'))['total'] or 0

        net_salary = emp.salary - fines_total + bonus_total

        total_hours_all += hours
        total_lates_all += lates
        total_fines_all += fines_total

        employee_stats.append({
            'employee': emp,
            'days_worked': days_worked,
            'hours_worked': round(hours, 1),
            'lates': lates,
            'fines_total': fines_total,
            'bonus_total': bonus_total,
            'net_salary': net_salary,
        })

    all_checkins = Attendance.objects.filter(
        date__year=year, date__month=month, check_in__isnull=False
    )
    avg_checkin = None
    if all_checkins.exists():
        total_seconds = sum(
            a.check_in.hour * 3600 + a.check_in.minute * 60 + a.check_in.second
            for a in all_checkins
        )
        avg_s = total_seconds // all_checkins.count()
        avg_checkin = f"{avg_s // 3600:02d}:{(avg_s % 3600) // 60:02d}"

    completed_projects = Project.objects.filter(status='completed').count()
    total_days = Attendance.objects.filter(
        date__year=year, date__month=month
    ).exclude(status='absent').count()
    total_possible = employees.count() * 22
    attendance_pct = round(total_days / total_possible * 100) if total_possible else 0

    context = {
        'employee_stats': employee_stats,
        'total_hours_all': round(total_hours_all, 1),
        'total_lates_all': total_lates_all,
        'total_fines_all': total_fines_all,
        'avg_checkin': avg_checkin,
        'completed_projects': completed_projects,
        'attendance_pct': attendance_pct,
        'year': year,
        'month': month,
        'month_name': months_ru[month],
        'tab': 'reports',
    }
    return render(request, 'bureau/reports.html', context)


# ─── Employees ───────────────────────────────────────────────────────────────

@login_required
@admin_only
def employees_view(request):
    employees = Employee.objects.all().order_by('full_name')

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add':
            full_name = request.POST.get('full_name')
            position = request.POST.get('position')
            salary = request.POST.get('salary', 0)
            phone = request.POST.get('phone', '')
            email = request.POST.get('email', '')
            hire_date = request.POST.get('hire_date')

            # Create User
            username = request.POST.get('username')
            password = request.POST.get('password')
            user_obj = None
            if username and password:
                if not User.objects.filter(username=username).exists():
                    user_obj = User.objects.create_user(username=username, password=password)
                else:
                    messages.error(request, 'Пользователь с таким логином уже существует')
                    return redirect('employees')

            Employee.objects.create(
                user=user_obj,
                full_name=full_name,
                position=position,
                salary=salary,
                phone=phone,
                email=email,
                hire_date=hire_date or datetime.date.today(),
            )
            messages.success(request, 'Сотрудник добавлен!')
        
        elif action == 'toggle_active':
            emp_id = request.POST.get('employee_id')
            emp = get_object_or_404(Employee, id=emp_id)
            emp.is_active = not emp.is_active
            emp.save()
            if emp.user:
                emp.user.is_active = emp.is_active
                emp.user.save()
            messages.success(request, 'Статус сотрудника изменён!')

        return redirect('employees')

    context = {
        'employees': employees,
        'positions': Employee.POSITION_CHOICES,
        'tab': 'employees',
    }
    return render(request, 'bureau/employees.html', context)


# ─── API ──────────────────────────────────────────────────────────────────────

def get_fine_amount_api(request):
    fine_type = request.GET.get('type', '')
    amount = Fine.FINE_AMOUNTS.get(fine_type, 0)
    return JsonResponse({'amount': amount})
