from django.contrib.auth.models import User
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Membuat user default gardenXi"

    def handle(self, *args, **options):
        username = "gardenXi"
        password = "passwordsuperaman"

        user, created = User.objects.get_or_create(username=username)
        user.set_password(password)
        user.is_staff = True
        user.is_superuser = True
        user.save()

        if created:
            self.stdout.write(self.style.SUCCESS("User gardenXi berhasil dibuat."))
        else:
            self.stdout.write(self.style.SUCCESS("User gardenXi berhasil diperbarui."))