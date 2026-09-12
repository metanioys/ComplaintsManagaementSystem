# --- START OF FILE accounts/utils.py ---

# تم الاستغناء عن مكتبة firebase_admin مؤقتاً بسبب الحظر التقني (Sanctions)

def send_push_notification(user, title, body, ticket_id=None):
    """
    دالة وهمية (Mock Function) تحاكي إرسال إشعارات فايربيس.
    بما أن خدمات جوجل محجوبة في سوريا، نقوم باعتراض طلب الإرسال
    وطباعته في الـ Console (Log) بدلاً من الاتصال بسيرفرات جوجل.
    هذا يمنع السيرفر من الانهيار ويحافظ على الـ API Contract مع الفرونت إند.
    """
    devices = user.devices.all()
    if not devices:
        return False # المستخدم ليس لديه أجهزة مسجلة

    # استخراج التوكنز فقط للطباعة (الوهمية)
    tokens = [device.fcm_token for device in devices]

    # تجهيز الـ Payload
    data_payload = {}
    if ticket_id:
        data_payload = {"ticket_id": str(ticket_id)}

    # طباعة الإشعار في الـ Terminal لكي تراقب النظام كمدير
    print("\n" + "="*50)
    print("🔔 [MOCK PUSH NOTIFICATION] - Firebase Disabled")
    print(f"📱 Targeted User: {user.email}")
    print(f"🔑 FCM Tokens: {len(tokens)} device(s) found")
    print(f"📝 Title: {title}")
    print(f"💬 Body: {body}")
    print(f"🔗 Payload: {data_payload}")
    print("="*50 + "\n")

    # نُرجع True لنوهم الـ Views أن الإرسال نجح (لكي يكتمل الكود بدون أخطاء)
    return True