import numpy as np
from scipy.optimize import least_squares

# 앵커 위치 (미터 단위)
anchor_positions = np.array([
    [0.0, 0.0],   # anchor1 위치
    [3.0, 0.0],   # anchor2 위치
    [3.0, 2.0],   # anchor3 위치
    [0.0, 2.0],   # anchor4 위치
])

# 보정된 타임스탬프 (초 단위)
corrected_timestamps = np.array([
    810.6040943776956,  # anchor1
    810.6040948086256,  # anchor2
    810.6040942137919,  # anchor3
    810.6070076174219   # anchor4
])

# 빛의 속도 (미터/초)
c = 299792458.0

def residuals(position, anchor_positions, corrected_timestamps):
    predicted_distances = np.sqrt(np.sum((anchor_positions - position) ** 2, axis=1))
    predicted_toas = predicted_distances / c
    return corrected_timestamps - predicted_toas

# 초기 위치 추정
initial_guess = np.array([0, 0])

# 비선형 최소제곱법으로 위치 추정
result = least_squares(residuals, initial_guess, args=(anchor_positions, corrected_timestamps))

# 추정된 위치
estimated_position = result.x
print(f"Estimated position: {estimated_position}")
