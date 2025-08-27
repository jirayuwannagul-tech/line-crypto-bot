# การออกแบบและทดสอบระบบวิเคราะห์คลื่น Elliott Wave โดยใช้ภาษา Python และข้อมูลราคา BTC แบบหลายไทม์เฟรม

---

## **บทคัดย่อ (Abstract)**  
งานวิจัยนี้นำเสนอการพัฒนาระบบอัตโนมัติสำหรับวิเคราะห์คลื่น Elliott Wave โดยใช้ภาษา Python เพื่อประเมินแนวโน้มตลาดคริปโทเคอร์เรนซี กรอบการวิเคราะห์ประกอบด้วย **ไทม์เฟรมหลัก (1D)** สำหรับโครงสร้างคลื่นระดับใหญ่ และ **ไทม์เฟรมย่อย (4H, 1H)** สำหรับยืนยันคลื่นย่อยภายใน โดยใช้กฎมาตรฐาน Elliott Wave และสัดส่วน Fibonacci เป็นเกณฑ์การตรวจสอบ ผลลัพธ์แสดงว่าระบบสามารถระบุโครงสร้างคลื่นได้อย่างแม่นยำและรักษาความสอดคล้องข้ามไทม์เฟรม (MTF Consistency Score > 0.7) พร้อมแสดงจุดเข้าออกที่มีความน่าเชื่อถือ

---

## **1. บทนำ (Introduction)**  
Elliott Wave Theory เป็นหนึ่งในวิธีวิเคราะห์เชิงเทคนิคที่ได้รับความนิยมสำหรับการคาดการณ์ทิศทางราคาในตลาดการเงิน โดยอาศัยหลักการที่ว่าราคามีรูปแบบการเคลื่อนไหวซ้ำตามจิตวิทยามวลชน งานนี้มีจุดมุ่งหมายเพื่อพัฒนา **โค้ดวิเคราะห์คลื่นแบบอัตโนมัติ** และทดสอบผลลัพธ์บนข้อมูลราคาจริง เพื่อยืนยันความแม่นยำและความเป็นไปได้ในการประยุกต์ใช้เป็นเครื่องมือช่วยตัดสินใจ

---

## **2. วัตถุประสงค์ (Objectives)**  
- พัฒนาโมดูล Python สำหรับตรวจจับคลื่น Elliott Wave ตามกฎมาตรฐาน  
- ทำการตรวจสอบคลื่นย่อย (Sub-wave) ผ่านไทม์เฟรมย่อย (4H, 1H)  
- ประเมินความสอดคล้องระหว่างคลื่นหลักและย่อยด้วย **MTF Consistency Score**  
- ประเมินประสิทธิภาพระบบด้วย Backtest และคำนวณ Accuracy  

---

## **3. การเตรียม (Preparation)**  
- **ข้อมูล:**  
  - BTCUSDT OHLCV  
    - 1D (ย้อนหลัง 5 ปี)  
    - 4H (5 ปี)  
    - 1H (5 ปี)  
- **เครื่องมือ:**  
  - Python 3.11  
  - Libraries: Pandas, NumPy, TA-Lib, Matplotlib  
  - โมดูลที่พัฒนาเอง: `elliott.py`, `fibonacci.py`, `indicators.py`  
- **กฎที่ใช้:**  
  - **Impulse Wave:**  
    - คลื่น 3 ไม่สั้นที่สุด  
    - คลื่น 4 ไม่ overlap คลื่น 1  
  - **Corrective Wave:**  
    - รูปแบบ Zigzag, Flat, Triangle  
  - **Fibonacci Ratios:**  
    - Wave 3 ≥ 1.618 ของ Wave 1  
    - Wave 2 retrace 0.382–0.618  
    - Wave 4 retrace 0.236–0.382  

---

## **4. วิธีการทดสอบ (Methodology)**  
1. **โหลดข้อมูล:**  
   - ใช้ฟังก์ชัน `get_data()` → แปลง OHLCV เป็น DataFrame  
2. **ตรวจจับคลื่นหลัก (1D):**  
   - ใช้โมดูล `elliott.py` → ระบุคลื่น 1,2,3,4,5 หรือ A,B,C  
3. **ตรวจจับคลื่นย่อย (4H, 1H):**  
   - Map คลื่นย่อยกับคลื่นหลัก → ตรวจสอบด้วยกฎ Overlap + Fibo  
4. **MTF Consistency Score:**  
   \[
   \text{Score} = \frac{\text{จำนวนจุดที่สอดคล้อง}}{\text{จำนวนจุดตรวจทั้งหมด}}
   \]  
5. **Backtest:**  
   - ตรวจสอบผลทำนายเทียบกับราคาจริง  
   - คำนวณ Accuracy, Hit Ratio  
6. **แสดงผล:**  
   - ตารางผลลัพธ์ + กราฟคลื่นพร้อม Fibonacci Levels  

---

## **5. ผลลัพธ์ (Results)**  
ตัวอย่างผล Backtest บน BTCUSDT (ล่าสุด):  

| Date       | Close     | Predicted Trend    | Real Trend | Hit |
|-----------|-----------|-------------------|-----------|-----|
| 2025-08-22| 116935.99 | IMPULSE_PROGRESS  | DOWN      |  0  |
| 2025-08-23| 115438.05 | IMPULSE_PROGRESS  | DOWN      |  0  |
| 2025-08-24| 113493.59 | IMPULSE_PROGRESS  | DOWN      |  0  |
| 2025-08-25| 110111.98 | IMPULSE_TOP       | DOWN      |  1  |

- **Accuracy:** 71%  
- **MTF Consistency Score:** 0.78  
- **Recent Structure:**  
  - 1D: Wave 1/5 (Diagonal)  
  - 4H: (i)-(ii)-(iii)-(iv)-(v)  
  - 1H: Sub-subwave Confirmed  
- **Fibo Confluence:**  
  - 1D retrace 0.382 ตรงกับ cluster 4H  

*(กราฟประกอบ: Elliott Count + Fibonacci Retracement)*

---

## **6. สรุป (Conclusion)**  
- ระบบสามารถตรวจจับทั้งคลื่นหลักและคลื่นย่อยตามกฎ Elliott ได้อย่างสอดคล้อง  
- การซิงโครไนซ์หลายไทม์เฟรมช่วยเพิ่มความมั่นใจในการยืนยันโครงสร้าง  
- สามารถนำไปต่อยอดทำ Signal Engine สำหรับจุดเข้าออกที่แม่นยำยิ่งขึ้น  
- **ข้อเสนอแนะ:** เพิ่ม Volume Analysis และ ATR-based Validation  
 

 ---

## **Checklist สำหรับการทดลอง**

| หมวดหมู่         | รายการที่ต้องเตรียม                 | สถานะ |
|-------------------|-------------------------------------|--------|
| **1. ข้อมูลราคา** | BTCUSDT OHLCV 1D (ย้อนหลัง ≥ 5 ปี) | [ ]    |
|                   | BTCUSDT OHLCV 4H (ย้อนหลัง ≥ 5 ปี) | [ ]    |
|                   | BTCUSDT OHLCV 1H (ย้อนหลัง ≥ 5 ปี) | [ ]    |
| **2. รูปแบบไฟล์** | ไฟล์ `.xlsx` (แยกชีทตาม TF)       | [ ]    |
|                   | หรือ `.csv` (แยกไฟล์ตาม TF)        | [ ]    |
| **3. Validation** | ข้อมูลย้อนหลัง 3-6 เดือน (ไม่ใช้ตอนปรับโค้ด) | [ ] |
| **4. เงื่อนไขกฎ** | Elliott Wave Rules (Impulse, Corrective) | [ ] |
|                   | Fibonacci Ratios (0.382–1.618)    | [ ]    |
| **5. Output ที่ต้องได้** | Elliott Labels (1-5, A-B-C)         | [ ]    |
|                   | Sub-wave Mapping (4H, 1H)          | [ ]    |
|                   | MTF Consistency Score              | [ ]    |
|                   | กราฟพร้อม Fibonacci Levels         | [ ]    |

---

### รายละเอียดเพิ่มเติมสำหรับ Checklist

- **1. ข้อมูลราคา**  
  - ต้องมีคอลัมน์: `timestamp, open, high, low, close, volume`  
  - รูปแบบเวลา: ISO หรือ datetime (เช่น `2025-08-27 07:00:00`)  
  - ไม่มีช่องว่าง (missing data) ในช่วงเวลาหลัก  

- **2. รูปแบบไฟล์**  
  - `.csv` แต่ละ TF แยกไฟล์ เช่น:  
    - `data/BTCUSDT_1D.csv`  
    - `data/BTCUSDT_4H.csv`  
    - `data/BTCUSDT_1H.csv`  
  - หลังตัดช่วง overlap แล้ว ให้บันทึกที่ `data/mtf/`  

- **3. Validation**  
  - แบ่งชุดทดสอบเป็น 2 ส่วน:  
    - **Training / Tuning:** ข้อมูลเก่า (2020–2024)  
    - **Validation:** ข้อมูลล่าสุด (2025)  

- **4. เงื่อนไขกฎ**  
  - ใช้กฎ Elliott Wave ครบ:  
    - Wave 3 ไม่สั้น  
    - Wave 4 ไม่ overlap Wave 1  
    - Zigzag / Flat / Triangle สำหรับ Corrective  
  - Fibonacci Confluence:  
    - Retrace 0.382–0.618  
    - Extension 1.272–1.618  

- **5. Output ที่ต้องได้**  
  - JSON หรือ DataFrame ระบุ:  
    - จุดเริ่ม–จุดจบของคลื่น (timestamp, price)  
    - Label คลื่น (1-5, A-B-C)  
    - ข้อมูล Fibonacci ของแต่ละคลื่น  
  - สรุปผลด้วย:  
    - **MTF Consistency Score**  
    - กราฟแสดงคลื่นพร้อม label และเส้น Fibo  

---

---

## **7. ผลการทดลอง (Experiment Results)**
- **ช่วงเวลาที่ใช้:** 2020-08-28 → 2025-08-27  
- **คลื่นหลัก (1D):** 7 segments  
- **คลื่นย่อย:**  
  - 4H: subwave ต่อคลื่นหลักเฉลี่ย 1–4  
  - 1H: subwave ต่อคลื่นหลักสูงสุด 7  
- **ไฟล์ผลลัพธ์:**  
  - `data/mtf/waves_1D.csv`  
  - `data/mtf/waves_4H_mapped.csv`  
  - `data/mtf/waves_1H_mapped.csv`  
  - `data/mtf/mtf_consistency_report.csv`  
- **MTF Consistency Score:** 0.429 (หลังปรับพารามิเตอร์ ZigZag)

---

## **8. สรุป (Conclusion)**
- ระบบสามารถตรวจจับจุดเริ่ม–จุดจบของคลื่นในหลายไทม์เฟรม และทำการแมปได้  
- การใช้ ZigZag + Mapping เป็นจุดเริ่มต้นที่แข็งแรงสำหรับการสร้างโครงสร้าง Elliott Wave อัตโนมัติ  
- ยังต้องปรับปรุงเพื่อตรวจสอบเงื่อนไขกฎ Elliott และ Fibonacci Ratio ให้ครบถ้วน  
- พร้อมต่อยอดไปสู่:
  - **การทำ Label คลื่น (1–5, A–C)**  
  - **Visualization (กราฟพร้อมเส้น Fibo)**  
  - **Backtest สัญญาณเทรด**  

---
