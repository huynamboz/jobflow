"""027: snapshot each existing employee's CV into an active EmployeeCV version.

Employees whose parse currently lives on the Employee row get one active
version mirroring it, so the new versions UI is consistent with what ranks.
"""
from django.db import migrations


def forward(apps, schema_editor):
    Employee = apps.get_model("employees", "Employee")
    EmployeeCV = apps.get_model("employees", "EmployeeCV")
    for emp in Employee.objects.exclude(cv_file="").exclude(cv_file=None):
        if EmployeeCV.objects.filter(employee=emp, is_active=True).exists():
            continue
        EmployeeCV.objects.create(
            employee=emp,
            cv_file=emp.cv_file.name,
            position=emp.position,
            seniority=emp.seniority,
            experience_years=emp.experience_years,
            skills=list(emp.skills or []),
            parsed_at=emp.parsed_at,
            is_parse_failed=emp.is_parse_failed,
            is_active=True,
        )


def backward(apps, schema_editor):
    apps.get_model("employees", "EmployeeCV").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [("employees", "0009_employeecv")]
    operations = [migrations.RunPython(forward, backward)]
