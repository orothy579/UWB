from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
import numpy as np
from scipy.optimize import least_squares
import logging

# Flask application setup
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tdoa.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Logger setup
logging.basicConfig(level=logging.DEBUG)
app.logger.setLevel(logging.DEBUG)

# Anchor positions (unit: meters)
anchor_positions = [
    (0.0, 0.0),    # Anchor 1 position
    (3.0, 0.0),    # Anchor 2 position
    (3.0, 2.0),    # Anchor 3 position
    (0.0, 2.0)     # Anchor 4 position
]

def h(si, corrected_timestamps):
    t1_i = corrected_timestamps[0]
    c = 299792458  # Speed of light (m/s)
    h_vec = []

    for n in range(1, len(corrected_timestamps)):
        tn_i = corrected_timestamps[n]
        rho_n_i = np.sqrt((anchor_positions[n][0] - si[0])**2 + (anchor_positions[n][1] - si[1])**2)
        rho_1_i = np.sqrt((anchor_positions[0][0] - si[0])**2 + (anchor_positions[0][1] - si[1])**2)

        if rho_n_i == 0 or rho_1_i == 0:
            raise ValueError("Rho value is zero")

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

        if rho_n_i == 0 or rho_1_i == 0:
            raise ValueError("Rho value is zero")

        H[n-1, 0] = (x - xn) / rho_n_i - (x - x1) / rho_1_i
        H[n-1, 1] = (y - yn) / rho_n_i - (y - y1) / rho_1_i

    return H

def ekf_update(si, corrected_timestamps):
    H = jacobian(si, corrected_timestamps)
    h_si = h(si, corrected_timestamps)
    
    residual = h_si - np.dot(H, si)
    app.logger.debug(f"Residual for position {si}: {residual}")

    return residual

def estimate_position(corrected_timestamps):
    # Use the center of anchor positions as the initial guess
    initial_guess = np.mean(anchor_positions, axis=0)
    
    result = least_squares(ekf_update, initial_guess, args=(corrected_timestamps,))
    return result.x

# Example corrected timestamps (small values for stability)
corrected_timestamps = [
    48424.62996190411 ,
    -14843.668713877067 ,
    -30991.150838158588, 
    1173.9667155073346 
]

original_timestamps = [ts / (15.65 * 10**-12) for ts in corrected_timestamps]


# Estimate the tag position
estimated_position = estimate_position(original_timestamps)
print(f"Estimated position: {estimated_position}")
