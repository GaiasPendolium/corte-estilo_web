import os

from django.contrib.auth import get_user_model
from django.db.models.signals import post_migrate
from django.dispatch import receiver


@receiver(post_migrate)
def ensure_deploy_admin(sender, **kwargs):
    """Create/update deploy admin user when env vars are provided."""
    if getattr(sender, "name", "") != "api":
        return

    username = os.environ.get("ADMIN_USERNAME")
    password = os.environ.get("ADMIN_PASSWORD")
    full_name = os.environ.get("ADMIN_FULL_NAME", "Administrador")

    # Only seed admin when explicitly configured in environment.
    if not username or not password:
        return

    User = get_user_model()
    user = User.objects.filter(username=username).first()

    if user is None:
        User.objects.create_superuser(
            username=username,
            password=password,
            nombre_completo=full_name,
            rol="administrador",
            activo=True,
            is_active=True,
        )
        return

    updated = False
    if not user.check_password(password):
        user.set_password(password)
        updated = True
    if getattr(user, "rol", None) != "administrador":
        user.rol = "administrador"
        updated = True
    if not getattr(user, "is_staff", False):
        user.is_staff = True
        updated = True
    if not getattr(user, "is_superuser", False):
        user.is_superuser = True
        updated = True
    if not getattr(user, "activo", True):
        user.activo = True
        updated = True
    if not getattr(user, "is_active", True):
        user.is_active = True
        updated = True

    if updated:
        user.save()
