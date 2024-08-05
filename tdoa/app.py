import pytz
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
import datetime
import numpy as np
from scipy.optimize import least_squares
import logging
import requests

# Flask 애플리케이션 설정
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tdoa.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 로거 설정
logging.basicConfig(level=logging.DEBUG)
app.logger.setLevel(logging.DEBUG)

# SQLAlchemy 인스턴스 생성
db = SQLAlchemy(app)

class Timestamp(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    anchor_id = db.Column(db.String(50))
    timestamp = db.Column(db.BigInteger)
    frame_type = db.Column(db.String(50))  # 'sync' or 'tag'
    sequence_number = db.Column(db.Integer)
    received_at = db.Column(db.DateTime, default=lambda: datetime.datetime.now(pytz.timezone('Asia/Seoul')))

class ClockModel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    anchor_id = db.Column(db.String(50), unique=True)
    offset = db.Column(db.Float)
    drift = db.Column(db.Float)

class TagPosition(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tag_id = db.Column(db.String(50))
    x = db.Column(db.Float)
    y = db.Column(db.Float)
    timestamp = db.Column(db.BigInteger)

with app.app_context():
    db.create_all()

# 앵커 위치 정의 (단위: 미터)
anchor_positions = [
    (0.0, 0.0),    # Anchor 1 위치
    (3.0, 0.0),    # Anchor 2 위치
    (3.0, 2.0),    # Anchor 3 위치
    (0.0, 2.0)     # Anchor 4 위치
]

@app.route('/api/timestamps', methods=['POST'])
def receive_timestamp():
    data = request.get_json()
    app.logger.debug(f"Received timestamp data: {data}")

    if not data:
        app.logger.error("No data provided")
        return jsonify({'message': 'No data provided'}), 400
    
    anchor_id = data.get('anchor_id')
    timestamp = data.get('timestamp')
    frame_type = data.get('frame_type')  # 'sync' or 'tag'
    sequence_number = data.get('sequence_number')

    if not anchor_id or timestamp is None or not frame_type or sequence_number is None:
        app.logger.error("Missing data fields")
        return jsonify({'message': 'Missing data fields'}), 400

    new_timestamp = Timestamp(anchor_id=anchor_id, timestamp=timestamp, frame_type=frame_type, sequence_number=sequence_number)
    db.session.add(new_timestamp)
    db.session.commit()
    
    app.logger.debug(f"Saved new timestamp: {new_timestamp}")

    if frame_type == 'sync':
        sync_timestamps = Timestamp.query.filter_by(anchor_id=anchor_id, frame_type='sync').order_by(Timestamp.received_at).all() 
        update_clock_model(anchor_id, sync_timestamps)

    if frame_type == 'tag':
        calculate_position_if_all_anchors_received(sequence_number)

    return jsonify({'message': 'Timestamp received'}), 200

def calculate_position_if_all_anchors_received(sequence_number):
    tag_timestamps = Timestamp.query.filter_by(frame_type='tag', sequence_number=sequence_number).all()
    if len(tag_timestamps) < len(anchor_positions):
        app.logger.debug(f"Not all anchors have received the tag signal for sequence number {sequence_number}")
        return

    timestamps_dict = {t.anchor_id: t.timestamp for t in tag_timestamps}
    calculate_and_send_position(sequence_number, timestamps_dict)

def calculate_and_send_position(sequence_number, timestamps_dict):
    tag_timestamps = timestamps_dict
    data = {
        "tag_id": "tag",
        "timestamps": tag_timestamps
    }

    url = "http://192.168.50.196:5000/api/calculate_position"
    response = requests.post(url, json=data)
    
    if response.status_code == 200:
        try:
            response_json = response.json()
            app.logger.debug(f"Position calculation response: {response_json}")
        except ValueError:
            app.logger.error("Failed to decode JSON response")
    else:
        app.logger.error(f"Failed to calculate position, status code: {response.status_code}")

def update_clock_model(anchor_id, sync_timestamps):
    if len(sync_timestamps) < 2:
        app.logger.debug(f"Not enough sync timestamps to update clock model for anchor {anchor_id}")
        return  # 최소 두 개의 동기화 타임스탬프가 필요합니다

    # 가장 최근의 두 동기화 타임스탬프를 가져옵니다.
    ts_n_k = sync_timestamps[-1]
    ts_n_k_minus_1 = sync_timestamps[-2]

    k = ts_n_k.sequence_number
    k_minus_1 = ts_n_k_minus_1.sequence_number
    tau_s = 503 * 15.65 * 10**-12

    tr_k = k * tau_s

    E_n_k = ts_n_k.timestamp * 15.65 * 10**-12 - tr_k
    E_n_k_minus_1 = ts_n_k_minus_1.timestamp * 15.65 * 10**-12 - (k_minus_1 * tau_s)

    i_n_k = (E_n_k - E_n_k_minus_1) / tau_s

    clock_model = ClockModel.query.filter_by(anchor_id=anchor_id).first()
    if clock_model is None:
        clock_model = ClockModel(anchor_id=anchor_id, offset=E_n_k, drift=i_n_k)
        app.logger.debug(f"Created new clock model for anchor {anchor_id}: {clock_model}")
    else:
        clock_model.offset = E_n_k
        clock_model.drift = i_n_k
        app.logger.debug(f"Updated clock model for anchor {anchor_id}: {clock_model}")

    db.session.add(clock_model)
    db.session.commit()


def calculate_positioning_timestamp(anchor_id, tag_timestamp, sync_timestamps):
    app.logger.debug(f"Calculating positioning timestamp for anchor {anchor_id}")
    clock_model = ClockModel.query.filter_by(anchor_id=anchor_id).first()
    if clock_model is None:
        app.logger.debug(f"No clock model found for anchor {anchor_id}, returning original timestamp")
        return tag_timestamp.timestamp

    ts_n_k = sync_timestamps[-1]

    tag_time_in_seconds = tag_timestamp.timestamp * 15.65 * 10**-12
    sync_time_in_seconds = ts_n_k.timestamp * 15.65 * 10**-12

    E_n_i = clock_model.offset + clock_model.drift * (tag_time_in_seconds - sync_time_in_seconds)

    corrected_timestamp = tag_time_in_seconds - E_n_i
    app.logger.debug(f"Calculated corrected timestamp for anchor {anchor_id}: {corrected_timestamp}")

    return corrected_timestamp


@app.route('/api/calculate_position', methods=['POST'])
def calculate_position():
    tag_data = request.get_json()
    app.logger.debug(f"Received tag data: {tag_data}")

    if not tag_data or not isinstance(tag_data.get('timestamps'), dict):
        app.logger.error("Invalid data provided")
        return jsonify({'message': 'Invalid data provided'}), 400

    tag_timestamps = tag_data.get('timestamps')
    tag_id = tag_data.get('tag_id')

    corrected_timestamps = []
    for anchor_id, ts in tag_timestamps.items():
        tag_timestamp = Timestamp.query.filter_by(anchor_id=anchor_id, frame_type='tag', timestamp=ts).first()
        if tag_timestamp is None:
            app.logger.error(f"Timestamp for anchor {anchor_id} with timestamp {ts} not found")
            return jsonify({'message': f'Timestamp for anchor {anchor_id} not found'}), 404
        
        sync_timestamps = Timestamp.query.filter_by(anchor_id=anchor_id, frame_type='sync').order_by(Timestamp.sequence_number).all()


        corrected_timestamp = calculate_positioning_timestamp(anchor_id, tag_timestamp,sync_timestamps)
        if not np.isfinite(corrected_timestamp):
            app.logger.error(f"Corrected timestamp for anchor {anchor_id} is not finite: {corrected_timestamp}")
            return jsonify({'message': f'Corrected timestamp for anchor {anchor_id} is not finite'}), 400

        app.logger.debug(f"Corrected timestamp for anchor {anchor_id}: {corrected_timestamp}")
        corrected_timestamps.append(corrected_timestamp)

    estimated_position = estimate_position(corrected_timestamps)
    x, y = estimated_position.tolist()
    app.logger.debug(f"Estimated position: {estimated_position}")

    new_tag_position = TagPosition(tag_id=tag_id, x=x, y=y, timestamp=int(datetime.datetime.now().timestamp()))
    db.session.add(new_tag_position)
    db.session.commit()
    app.logger.debug(f"Saved new tag position: {new_tag_position}")

    return jsonify({'estimated_position': [x, y]}), 200

def h(si, corrected_timestamps):
    t1_i = corrected_timestamps[0]
    c = 299792458  # 빛의 속도 (m/s)
    h_vec = []

    for n in range(1, len(corrected_timestamps)):
        tn_i = corrected_timestamps[n]
        rho_n_i = np.sqrt((anchor_positions[n][0] - si[0])**2 + (anchor_positions[n][1] - si[1])**2)
        rho_1_i = np.sqrt((anchor_positions[0][0] - si[0])**2 + (anchor_positions[0][1] - si[1])**2)

        if rho_n_i == 0 or rho_1_i == 0:
            app.logger.error(f"Rho value is zero for anchor {n}")
            raise ValueError("Rho value is zero")

        h_vec.append(c * (tn_i - t1_i) - (rho_n_i - rho_1_i))

    app.logger.debug(f"h vector: {h_vec}")
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
            app.logger.error(f"Rho value is zero for anchor {n}")
            raise ValueError("Rho value is zero")

        H[n-1, 0] = (x - xn) / rho_n_i - (x - x1) / rho_1_i
        H[n-1, 1] = (y - yn) / rho_n_i - (y - y1) / rho_1_i

    if np.isnan(H).any():
        app.logger.error("Jacobian matrix contains NaN values")
        raise ValueError("Jacobian matrix contains NaN values")

    app.logger.debug(f"Jacobian matrix: {H}")
    return H

def ekf_update(si, corrected_timestamps):
    H = jacobian(si, corrected_timestamps)
    h_si = h(si, corrected_timestamps)
    
    residual = h_si - np.dot(H, si)
    app.logger.debug(f"Residual: {residual}")
    return residual

def estimate_position(corrected_timestamps):
    # 앵커 위치의 중심점을 초기 추정값으로 사용
    initial_guess = np.mean(anchor_positions, axis=0)
    app.logger.debug(f"Initial guess for position: {initial_guess}")
    
    result = least_squares(ekf_update, initial_guess, args=(corrected_timestamps,))
    app.logger.debug(f"Estimated position: {result.x}")

    return result.x


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
