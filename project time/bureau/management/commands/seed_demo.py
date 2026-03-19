import datetime
from django.core.management.base import BaseCommand
from bureau.models import Employee, Attendance, Project, Fine, Bonus


class Command(BaseCommand):
    help = 'Загрузка демо-данных для Архитектурного бюро'

    def handle(self, *args, **options):
        # Clear existing
        Fine.objects.all().delete()
        Bonus.objects.all().delete()
        Attendance.objects.all().delete()
        Project.objects.all().delete()
        Employee.objects.all().delete()

        # Create employees (exactly as shown in screenshots)
        employees_data = [
            {'full_name': 'Асель Каримова',  'position': 'lead_architect', 'salary': 350000},
            {'full_name': 'Берик Нурланов',  'position': 'architect',      'salary': 280000},
            {'full_name': 'Диана Сейткали',  'position': 'constructor',    'salary': 240000},
            {'full_name': 'Марат Ахметов',   'position': 'designer',       'salary': 260000},
            {'full_name': 'Айгерим Бекова',  'position': 'architect',      'salary': 250000},
        ]
        employees = []
        for d in employees_data:
            emp = Employee.objects.create(**d)
            employees.append(emp)
            self.stdout.write(f'  Создан сотрудник: {emp.full_name}')

        asel, berik, diana, marat, aigеrim = employees

        today = datetime.date.today()
        march = datetime.date(today.year, 3, 17)

        # Today attendance (as per screenshot)
        Attendance.objects.create(
            employee=asel, date=today,
            check_in=datetime.time(8, 52), status='present')
        Attendance.objects.create(
            employee=berik, date=today,
            check_in=datetime.time(9, 14), status='late', late_minutes=14)
        Attendance.objects.create(
            employee=diana, date=today,
            check_in=datetime.time(9, 31), status='late', late_minutes=31)
        Attendance.objects.create(
            employee=aigеrim, date=today,
            check_in=datetime.time(8, 45),
            check_out=datetime.time(18, 2), status='left')

        # Historical attendance for March (for reports)
        for day_num in range(1, 17):
            d = datetime.date(today.year, 3, day_num)
            if d.weekday() >= 5:
                continue
            for emp in employees:
                late_min = 0
                status = 'present'
                ci = datetime.time(8, 45 + (emp.id % 10))
                co = datetime.time(18, 0)
                if emp == diana and day_num % 4 == 0:
                    ci = datetime.time(9, 15 + (day_num % 20))
                    late_min = 15 + (day_num % 20)
                    status = 'late'
                elif emp == berik and day_num == 12:
                    ci = datetime.time(9, 14)
                    late_min = 14
                    status = 'late'
                elif emp == marat and day_num % 6 == 0:
                    ci = datetime.time(9, 10)
                    late_min = 10
                    status = 'late'
                Attendance.objects.get_or_create(
                    employee=emp, date=d,
                    defaults={'check_in': ci, 'check_out': co,
                              'status': status, 'late_minutes': late_min})

        # Projects (as per screenshot)
        projects_data = [
            {'name': 'Жилой комплекс "Нур"',    'description': 'Финальные чертежи',      'responsible': asel,
             'deadline': datetime.date(today.year, 3, 19), 'progress': 78,  'status': 'in_progress', 'stage': 'drawing'},
            {'name': 'БЦ "Алатау Плаза"',        'description': 'Согласование фасада',    'responsible': berik,
             'deadline': datetime.date(today.year, 3, 22), 'progress': 55,  'status': 'in_progress', 'stage': 'approval'},
            {'name': 'Школа №45 — реконструкция', 'description': 'Эскизный проект',       'responsible': diana,
             'deadline': datetime.date(today.year, 4, 5),  'progress': 30,  'status': 'in_progress', 'stage': 'sketch'},
            {'name': 'Частный дом "Алма"',        'description': 'Рабочий проект',         'responsible': marat,
             'deadline': datetime.date(today.year, 4, 15), 'progress': 90,  'status': 'review',      'stage': 'working_project'},
            {'name': 'Торговый центр "Каскад"',   'description': 'Генплан',                'responsible': aigеrim,
             'deadline': datetime.date(today.year, 3, 30), 'progress': 100, 'status': 'completed',   'stage': 'handover'},
        ]
        for pd in projects_data:
            p = Project.objects.create(**pd)
            self.stdout.write(f'  Создан проект: {p.name}')

        # Fines for March (as per screenshot)
        fines_data = [
            {'employee': diana,  'fine_type': 'late_over_30',  'amount': 5000,  'date': datetime.date(today.year, 3, 17), 'reason': 'Опоздание (31 мин)'},
            {'employee': marat,  'fine_type': 'absence',        'amount': 15000, 'date': datetime.date(today.year, 3, 17), 'reason': 'Прогул'},
            {'employee': berik,  'fine_type': 'deadline_7',     'amount': 20000, 'date': datetime.date(today.year, 3, 12), 'reason': 'Просрочка дедлайна'},
            {'employee': diana,  'fine_type': 'late_under_30',  'amount': 2500,  'date': datetime.date(today.year, 3, 10), 'reason': 'Опоздание (15 мин)'},
            {'employee': marat,  'fine_type': 'bad_quality',    'amount': 5000,  'date': datetime.date(today.year, 3, 5),  'reason': 'Некачественная сдача чертежей'},
        ]
        for fd in fines_data:
            Fine.objects.create(**fd)
        self.stdout.write(f'  Создано штрафов: {len(fines_data)}')

        # Bonus for Asel
        Bonus.objects.create(
            employee=asel, amount=35000,
            date=datetime.date(today.year, 3, 1),
            reason='Бонус за качественную работу')

        self.stdout.write(self.style.SUCCESS('\n✅ Демо-данные успешно загружены!'))
        self.stdout.write('   Сотрудников: 5 | Проектов: 5 | Штрафов: 5')
