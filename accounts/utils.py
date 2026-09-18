
def send_push_notification(user, title, body, ticket_id=None):
    
    devices = user.devices.all()
    if not devices:
        return False 

    tokens = [device.fcm_token for device in devices]

    data_payload = {}
    if ticket_id:
        data_payload = {"ticket_id": str(ticket_id)}

    print("\n" + "="*50)
    print("🔔 [MOCK PUSH NOTIFICATION] - Firebase Disabled")
    print(f"📱 Targeted User: {user.email}")
    print(f"🔑 FCM Tokens: {len(tokens)} device(s) found")
    print(f"📝 Title: {title}")
    print(f"💬 Body: {body}")
    print(f"🔗 Payload: {data_payload}")
    print("="*50 + "\n")

    return True