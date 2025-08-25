import cv2
import pytesseract
import re

# โหลดรูป
img = cv2.imread("wave_chart.png")
if img is None:
    print("❌ ไม่เจอไฟล์ wave_chart.png")
    exit()

# Preprocess
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
_, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)

# Invert สี
invert = cv2.bitwise_not(thresh)
cv2.imwrite("invert.png", invert)

# OCR whitelist เฉพาะ 12345ABC
custom_config = r'-c tessedit_char_whitelist=12345ABC --psm 6'
text = pytesseract.image_to_string(invert, config=custom_config)

print("\n📜 OCR Output:")
print(text)

# ดึงเฉพาะคลื่น
waves = re.findall(r"[12345ABC]", text)
print("\n🎯 Detected Waves:", waves)
