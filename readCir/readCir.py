import serial
import matplotlib.pyplot as plt
import matplotlib.animation as animation

# 시리얼 포트 설정 (ESP32가 연결된 포트로 변경)
ser = serial.Serial('COM5', 115200, timeout=1)

real_values = []
imag_values = []
amplitude = []

fig, ax = plt.subplots()
line, = ax.plot([], [], lw=2)
ax.set_ylim(0, 5000)  # y축 범위를 데이터에 맞게 설정하세요
ax.set_xlim(0, 992)
ax.grid()

def init():
    line.set_data([], [])
    return line,

def update(data):
    real, imag = data
    real_values.append(real)
    imag_values.append(imag)
    if len(real_values) > 992:
        real_values.pop(0)
        imag_values.pop(0)
    amplitude = [((r**2 + i**2)**0.5) for r, i in zip(real_values, imag_values)]
    line.set_data(range(len(real_values)), amplitude)
    return line,

def data_gen():
    while True:
        line = ser.readline().decode('utf-8').strip()
        if line:
            try:
                real, imag = map(int, line.split(','))
                yield real, imag
            except ValueError:
                continue

ani = animation.FuncAnimation(fig, update, data_gen, init_func=init, blit=True, interval=50)
plt.show()
