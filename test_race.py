import threading
import requests

# تأكد أن الرابط يطابق تماماً الرابط الموجود في ملف urls.py لديك
URL = "http://127.0.0.1:8000/orders/place-order/"

def send_order(i):
    try:
        # إرسال طلب POST للمنتج رقم 4 بكمية 1
        response = requests.post(URL, json={"product_id": 4, "quantity": 1}, timeout=10)
        
        # لضمان طباعة الحروف العربية بوضوح في Terminal الويندوز دون رموز غريبة
        response.encoding = 'utf-8' 
        
        print(f"Thread {i:02d}: Status {response.status_code} | Response: {response.text}")
    except Exception as e:
        print(f"Thread {i:02d}: ERROR - {e}")

# إنشاء 50 خيط (Thread) لمحاكاة 50 مستخدم في نفس اللحظة
threads = [threading.Thread(target=send_order, args=(i,)) for i in range(50)]

# تشغيل جميع الخيوط معاً بسرعة
for t in threads:
    t.start()

# انتظار انتهاء جميع الخيوط قبل طباعة الكلمة الأخيرة
for t in threads:
    t.join()

print("\n=== 50")
