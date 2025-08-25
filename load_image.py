import cv2

img = cv2.imread("wave_chart.png")

if img is None:
    print("❌ ไม่เจอไฟล์รูป")
else:
    print("✅ โหลดรูปสำเร็จ ขนาด:", img.shape)

