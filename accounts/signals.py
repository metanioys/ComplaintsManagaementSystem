from django.db.models.signals import post_save, post_migrate
from django.dispatch import receiver
from django.contrib.auth.models import Group
from .models import CustomUser

@receiver(post_migrate)
def create_default_groups(sender, **kwargs):
    if sender.name == 'accounts':
        groups = ['citizen', 'tier1_dispatcher', 'tier2_liaison', 'super_admin']
        for group_name in groups:
            Group.objects.get_or_create(name=group_name)

@receiver(post_save, sender=CustomUser)
def assign_default_role(sender, instance, created, **kwargs):
    if created:
        if not instance.is_superuser and not instance.is_staff:
            citizen_group, _ = Group.objects.get_or_create(name='citizen')
            instance.groups.add(citizen_group)