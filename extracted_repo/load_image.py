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

# 4) Invert สี (กลับดำ ↔ ขาว)
invert = cv2.bitwise_not(thresh)
cv2.imwrite("invert.png", invert)

# 5) OCR โดย whitelist เฉพาะตัวเลข/อักษร 12345ABC
custom_config = r'-c tessedit_char_whitelist=12345ABC --psm 6'
text = pytesseract.image_to_string(invert, config=custom_config)

print("\n📜 OCR Output (Raw):")
print(text)

# 6) ดึงเฉพาะตัวเลข/อักษรที่เป็น Wave
waves = re.findall(r"[12345ABC]", text)
print("\n🎯 Detected Waves:", waves)

# 7) แสดงภาพสุดท้ายที่ใช้ OCR
plt.imshow(invert, cmap="gray")
plt.title("Image used for OCR (invert)")
plt.axis("off")
plt.show()
