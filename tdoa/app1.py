import numpy as np
from scipy.optimize import least_squares

TIMESTAMP_CONVERSION_FACTOR = 1 / (128 * 499.2 * 10**6)


print(TIMESTAMP_CONVERSION_FACTOR)

tau_s = 0.2 / TIMESTAMP_CONVERSION_FACTOR # sec

print(tau_s)


# 빛의 속도 (m/s)
c = 299792458  

# 앵커 위치 (단위: 미터)
anchor_positions = [
    (0.0, 0.0),    # Anchor 1 위치
    (3.0, 0.0),    # Anchor 2 위치
    (3.0, 2.0),    # Anchor 3 위치
    (0.0, 2.0)     # Anchor 4 위치
]

corrected_timestamps = [
    9094440249109.896,  # Anchor 1
    9094440248766.375,  # Anchor 2
    9094440248414.674,  # Anchor 3
    9094440249690.8     # Anchor 4
]

# TDOA 계산
t1_i = corrected_timestamps[0]
tdoa = [(t - t1_i) * TIMESTAMP_CONVERSION_FACTOR for t in corrected_timestamps]

# 거리 차이 계산
distance_diffs = [c * t for t in tdoa]

# 비선형 방정식을 풀기 위한 목표 함수 정의
def residuals(position, anchor_positions, distance_diffs):
    residuals = []
    for i in range(1, len(anchor_positions)):
        distance_actual = np.sqrt((position[0] - anchor_positions[i][0])**2 + (position[1] - anchor_positions[i][1])**2)
        distance_ref = np.sqrt((position[0] - anchor_positions[0][0])**2 + (position[1] - anchor_positions[0][1])**2)
        residuals.append(distance_actual - distance_ref - distance_diffs[i])
    return residuals

# 초기 추정치 (임의로 중앙에 설정)
initial_guess = [1.5, 1.5]

# 가우스-뉴턴 방법을 사용하여 최적화 실행
result = least_squares(residuals, initial_guess, args=(anchor_positions, distance_diffs), method='lm')

# 최적화된 위치 출력
estimated_position = result.x
print(f"Estimated Position: x = {estimated_position[0]}, y = {estimated_position[1]}")
