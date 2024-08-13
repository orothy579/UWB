import numpy as np
from scipy.optimize import least_squares

corrected_timestamps = {
    'anchor1': 22.95152156981062,
    'anchor2': 17.32371431879711,
    'anchor3': 18.70568657628561,
    'anchor4': 22.954165383345263
}

anchor_positions = [
    (0.0, 0.0),    # anchor1 위치
    (3.0, 0.0),    # anchor2 위치
    (3.0, 2.0),    # anchor3 위치
    (0.0, 2.0)     # anchor4 위치
]



def h(si, corrected_timestamps):
    t1_i = corrected_timestamps[0]
    c = 299792458  # 빛의 속도 (m/s)
    h_vec = []

    for n in range(1, len(corrected_timestamps)):
        tn_i = corrected_timestamps[n]
        rho_n_i = np.sqrt((anchor_positions[n][0] - si[0])**2 + (anchor_positions[n][1] - si[1])**2)
        rho_1_i = np.sqrt((anchor_positions[0][0] - si[0])**2 + (anchor_positions[0][1] - si[1])**2)
        h_vec.append(c * (tn_i - t1_i) - (rho_n_i - rho_1_i))

    return np.array(h_vec)

def jacobian(si, corrected_timestamps):
    x, y = si
    H = np.zeros((len(corrected_timestamps) - 1, 2))

    for n in range(1, len(corrected_timestamps)):
        xn, yn = anchor_positions[n]
        x1, y1 = anchor_positions[0]
        rho_n_i = np.sqrt((xn - x) ** 2 + (yn - y) ** 2)
        rho_1_i = np.sqrt((x1 - x) ** 2 + (y1 - y) ** 2)
        H[n-1, 0] = (x - xn) / rho_n_i - (x - x1) / rho_1_i
        H[n-1, 1] = (y - yn) / rho_n_i - (y - y1) / rho_1_i

    return H

def ekf_update(si, corrected_timestamps):
    H = jacobian(si, corrected_timestamps)
    h_si = h(si, corrected_timestamps)
    residual = h_si - np.dot(H, si)
    return residual

def estimate_position(corrected_timestamps):
    initial_guess = [1, 1]  # 초기 추정 위치 (x, y)
    result = least_squares(ekf_update, initial_guess, args=(corrected_timestamps,))
    return result.x

# Corrected timestamps in the correct order based on anchor positions
corrected_timestamps_ordered = [
    corrected_timestamps['anchor1'],
    corrected_timestamps['anchor2'],
    corrected_timestamps['anchor3'],
    corrected_timestamps['anchor4']
]

# 위치 추정 수행
estimated_position = estimate_position(corrected_timestamps_ordered)
x, y = estimated_position.tolist()

print(f"Estimated position: ({x}, {y})")
