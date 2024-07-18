import serial
import matplotlib.pyplot as plt
import numpy as np

# 시리얼 포트 설정 (포트 이름을 실제 사용 중인 포트로 변경)
ser = serial.Serial('COM5', 115200, timeout=1)

# 데이터 저장을 위한 리스트 초기화
real_parts = []
imaginary_parts = []
magnitudes = []
samples = []

# 데이터 읽기 함수
def read_serial_data():
    while True:
        try:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            if line:
                parts = line.split(',')
                if len(parts) == 3:
                    sample = int(parts[0])
                    real_part = int(parts[1])
                    imaginary_part = int(parts[2])
                    
                    samples.append(sample)
                    real_parts.append(real_part)
                    imaginary_parts.append(imaginary_part)
                    
                    # magnitude 계산
                    magnitude = np.sqrt(real_part**2 + imaginary_part**2)
                    magnitudes.append(magnitude)
                    
                    print(f"Sample {sample}: Real Part = {real_part}, Imaginary Part = {imaginary_part}, Magnitude = {magnitude}")
                    
                    if len(samples) >= 1016:  # 원하는 샘플 수를 다 읽으면 종료
                        break
        except Exception as e:
            print(f"Error reading line: {e}")

# 데이터 읽기
read_serial_data()

# 시리얼 포트 닫기
ser.close()

# 플롯 그리기
plt.figure(figsize=(12, 6))
plt.plot(samples, magnitudes, label='Magnitude')
plt.xlabel('Sample Index')
plt.ylabel('Magnitude')
plt.title('CIR Data Magnitude')
plt.legend()
plt.show()