from django.db import models
from django.utils.translation import gettext_lazy as _

class EmergencyAnnouncement(models.Model):
    id = models.AutoField(primary_key=True, verbose_name=_("رقم الإعلان"))
    message_ar = models.TextField(verbose_name=_("الرسالة بالعربي"))
    message_en = models.TextField(verbose_name=_("الرسالة بالإنجليزي"))
    is_visible = models.BooleanField(default=True, verbose_name=_("حالة الظهور"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("تاريخ الإنشاء"))
    # إذا كان الحقل فارغاً فهذا يعني أنه "إعلان وطني عام"، وإذا تم تحديد محافظات سيظهر لسكانها فقط
    governorates = models.ManyToManyField('complaints.Governorate', blank=True, related_name='announcements', verbose_name=_("المحافظات المستهدفة"))