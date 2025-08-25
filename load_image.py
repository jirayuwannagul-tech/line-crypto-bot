import cv2

# เปลี่ยนชื่อผู้ใช้เป็นของคุณจริง ๆ (เช่น jirayu_wannagulhotmail.com)
img = cv2.imread("/Users/jirayu_wannagulhotmail.com/Desktop/wave_chart.png")

if img is None:
    print("❌ ไม่เจอไฟล์รูป ลองเช็ค path อีกครั้ง")
else:
    print("✅ โหลดรูปสำเร็จ ขนาด:", img.shape)
