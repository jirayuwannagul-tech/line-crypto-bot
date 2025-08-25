import cv2
import pytesseract
import re
import matplotlib.pyplot as plt

# 1) โหลดรูป
img = cv2.imread("wave_chart.png")

if img is None:
    print("❌ ไม่เจอไฟล์ wave_chart.png - เช็ค path อีกครั้ง")
    exit()

print("✅ โหลดรูปสำเร็จ ขนาด:", img.shape)

# 2) แปลงเป็น grayscale
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
cv2.imwrite("gray.png", gray)

# 3) Blur + Threshold ให้ตัวเลขชัดขึ้น
blur = cv2.GaussianBlur(gray, (5, 5), 0)
_, thresh = cv2.threshold(blur, 150, 255, cv2.THRESH_BINARY)
cv2.imwrite("thresh.png", thresh)

# 4) OCR อ่านข้อความจากภาพ
text = pytesseract.image_to_string(thresh, lang="eng")
print("\n📜 Raw OCR output:")
print(text)

# 5) ดึงเฉพาะตัวเลข/ตัวอักษรที่เกี่ยวกับ Wave (1-5, A-C)
waves = re.findall(r"[12345ABC]", text)
print("\n🎯 Detected Waves:", waves)

# 6) (Optional) แสดงภาพ threshold เพื่อดูว่าชัดไหม
plt.imshow(thresh, cmap="gray")
plt.title("Threshold Image for OCR")
plt.axis("off")
plt.show()
