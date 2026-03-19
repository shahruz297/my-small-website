from django.db import models
from django.utils import timezone
from django.conf import settings
import datetime


from django.contrib.auth.models import User

class Employee(models.Model):
    POSITION_CHOICES = [
        ('architect', 'Архитектор'),
        ('lead_architect', 'Ведущий архитектор'),
        ('designer', 'Дизайнер'),
        ('constructor', 'Конструктор'),
        ('manager', 'Менеджер'),
        ('intern', 'Стажёр'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True, verbose_name='Пользователь', related_name='employee_profile')
    full_name = models.CharField(max_length=200, verbose_name='ФИО')
    position = models.CharField(max_length=50, choices=POSITION_CHOICES, verbose_name='Должность')
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True, verbose_name='Аватар')
    salary = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Оклад (тенге)')
    phone = models.CharField(max_length=20, blank=True, verbose_name='Телефон')
    email = models.EmailField(blank=True, verbose_name='Email')
    hire_date = models.DateField(default=datetime.date.today, verbose_name='Дата найма')
    is_active = models.BooleanField(default=True, verbose_name='Активен')
    created_at = models.DateTimeField(auto_now_add=True)

    def get_initials(self):
        parts = self.full_name.split()
        if len(parts) >= 2:
            return f"{parts[0][0]}{parts[1][0]}"
        return self.full_name[:2].upper()

    def get_position_display_ru(self):
        return dict(self.POSITION_CHOICES).get(self.position, self.position)

    def get_monthly_salary(self, year=None, month=None):
        if year is None or month is None:
            now = timezone.now()
            year, month = now.year, now.month
        total_fines = Fine.objects.filter(
            employee=self,
            date__year=year,
            date__month=month
        ).aggregate(total=models.Sum('amount'))['total'] or 0
        bonus = Bonus.objects.filter(
            employee=self,
            date__year=year,
            date__month=month
        ).aggregate(total=models.Sum('amount'))['total'] or 0
        return self.salary - total_fines + bonus

    def __str__(self):
        return f"{self.full_name} ({self.get_position_display()})"

    class Meta:
        verbose_name = 'Сотрудник'
        verbose_name_plural = 'Сотрудники'
        ordering = ['full_name']


class Attendance(models.Model):
    STATUS_CHOICES = [
        ('present', 'На месте'),
        ('late', 'Опоздание'),
        ('left', 'Ушла'),
        ('absent', 'Отсутствует'),
    ]

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='attendances', verbose_name='Сотрудник')
    date = models.DateField(default=datetime.date.today, verbose_name='Дата')
    check_in = models.TimeField(null=True, blank=True, verbose_name='Время прихода')
    check_out = models.TimeField(null=True, blank=True, verbose_name='Время ухода')
    check_in_photo = models.ImageField(upload_to='attendance_photos/', blank=True, null=True, verbose_name='Фото при приходе')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='absent', verbose_name='Статус')
    late_minutes = models.IntegerField(default=0, verbose_name='Опоздание (минут)')
    notes = models.TextField(blank=True, verbose_name='Примечания')

    def calculate_late_minutes(self):
        if self.check_in:
            work_start = datetime.time(settings.WORK_START_HOUR, settings.WORK_START_MINUTE)
            if self.check_in > work_start:
                check_in_dt = datetime.datetime.combine(datetime.date.today(), self.check_in)
                start_dt = datetime.datetime.combine(datetime.date.today(), work_start)
                delta = check_in_dt - start_dt
                return int(delta.total_seconds() / 60)
        return 0

    def get_hours_worked(self):
        if self.check_in and self.check_out:
            check_in_dt = datetime.datetime.combine(self.date, self.check_in)
            check_out_dt = datetime.datetime.combine(self.date, self.check_out)
            delta = check_out_dt - check_in_dt
            return round(delta.total_seconds() / 3600, 1)
        return 0

    def save(self, *args, **kwargs):
        if self.check_in:
            work_start = datetime.time(settings.WORK_START_HOUR, settings.WORK_START_MINUTE)
            self.late_minutes = self.calculate_late_minutes()
            if self.check_out:
                self.status = 'left'
            elif self.check_in > work_start:
                self.status = 'late'
            else:
                self.status = 'present'
        else:
            self.status = 'absent'
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.employee.full_name} — {self.date}"

    class Meta:
        verbose_name = 'Посещаемость'
        verbose_name_plural = 'Посещаемость'
        ordering = ['-date']
        unique_together = ['employee', 'date']


class Project(models.Model):
    STATUS_CHOICES = [
        ('in_progress', 'В работе'),
        ('review', 'На проверке'),
        ('completed', 'Завершён'),
    ]

    STAGE_CHOICES = [
        ('sketch', 'Эскиз'),
        ('drawing', 'Чертёж'),
        ('approval', 'Согласование'),
        ('working_project', 'Рабочий проект'),
        ('ganplan', 'Генплан'),
        ('handover', 'Сдан'),
    ]

    name = models.CharField(max_length=300, verbose_name='Название проекта')
    description = models.TextField(blank=True, verbose_name='Описание')
    responsible = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, related_name='projects', verbose_name='Ответственный')
    deadline = models.DateField(verbose_name='Дедлайн')
    progress = models.IntegerField(default=0, verbose_name='Прогресс (%)')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='in_progress', verbose_name='Статус')
    stage = models.CharField(max_length=30, choices=STAGE_CHOICES, default='sketch', verbose_name='Этап')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def days_until_deadline(self):
        today = datetime.date.today()
        delta = self.deadline - today
        return delta.days

    def is_overdue(self):
        return datetime.date.today() > self.deadline and self.status != 'completed'

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = 'Проект'
        verbose_name_plural = 'Проекты'
        ordering = ['deadline']


class Fine(models.Model):
    FINE_TYPE_CHOICES = [
        ('late_under_30', 'Опоздание до 30 мин'),
        ('late_over_30', 'Опоздание более 30 мин'),
        ('absence', 'Прогул без уважительной причины'),
        ('deadline_3', 'Просрочка дедлайна (до 3 дней)'),
        ('deadline_7', 'Просрочка дедлайна (3–7 дней)'),
        ('deadline_more', 'Просрочка дедлайна (более 7 дней)'),
        ('bad_quality', 'Некачественная сдача работы'),
        ('manual', 'Ручной штраф'),
    ]

    FINE_AMOUNTS = {
        'late_under_30': 2500,
        'late_over_30': 5000,
        'absence': 15000,
        'deadline_3': 10000,
        'deadline_7': 20000,
        'deadline_more': 35000,
        'bad_quality': 5000,
    }

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='fines', verbose_name='Сотрудник')
    fine_type = models.CharField(max_length=30, choices=FINE_TYPE_CHOICES, verbose_name='Тип штрафа')
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Сумма (тенге)')
    date = models.DateField(default=datetime.date.today, verbose_name='Дата')
    reason = models.TextField(blank=True, verbose_name='Причина')
    attendance = models.ForeignKey(Attendance, on_delete=models.SET_NULL, null=True, blank=True, related_name='fines', verbose_name='Запись посещаемости')

    def save(self, *args, **kwargs):
        if not self.amount and self.fine_type in self.FINE_AMOUNTS:
            self.amount = self.FINE_AMOUNTS[self.fine_type]
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.employee.full_name} — {self.get_fine_type_display()} — {self.amount} тг"

    class Meta:
        verbose_name = 'Штраф'
        verbose_name_plural = 'Штрафы'
        ordering = ['-date']


class Bonus(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='bonuses', verbose_name='Сотрудник')
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Сумма бонуса')
    date = models.DateField(default=datetime.date.today, verbose_name='Дата')
    reason = models.TextField(blank=True, verbose_name='Причина')

    def __str__(self):
        return f"{self.employee.full_name} — Бонус {self.amount} тг"

    class Meta:
        verbose_name = 'Бонус'
        verbose_name_plural = 'Бонусы'
        ordering = ['-date']
