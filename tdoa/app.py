import matplotlib
matplotlib.use('Agg') 

import pytz
from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
import datetime
import numpy as np
from scipy.optimize import least_squares
import logging
import requests
import matplotlib.pyplot as plt
import io
import base64

TIMESTAMP_CONVERSION_FACTOR = 1 / (128 * 499.2 * 10**6)


anchor_id_map = {
    'anchor1': 0,
    'anchor2': 1,
    'anchor3': 2,
    'anchor4': 3
}

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tdoa.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

logging.basicConfig(level=logging.DEBUG)
app.logger.setLevel(logging.DEBUG)

db = SQLAlchemy(app)

class Timestamp(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    anchor_id = db.Column(db.String(50))
    timestamp = db.Column(db.BigInteger)
    frame_type = db.Column(db.String(50))  
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

anchor_positions = [
    (0.0, 0.0),    
    (3.0, 0.0),    
    (3.0, 2.0),    
    (0.0, 2.0)     
]

@app.route('/api/timestamps', methods=['POST'])
def receive_timestamp():
    data = request.get_json()

    if not data:
        app.logger.error("No data provided")
        return jsonify({'message': 'No data provided'}), 400
    
    anchor_id = data.get('anchor_id')
    timestamp = data.get('timestamp')
    frame_type = data.get('frame_type')  
    sequence_number = data.get('sequence_number')

    if not anchor_id or timestamp is None or not frame_type or sequence_number is None:
        app.logger.error("Missing data fields")
        return jsonify({'message': 'Missing data fields'}), 400

    previous_entry_ts = Timestamp.query.filter_by(anchor_id=anchor_id).order_by(Timestamp.id.desc()).first()

    if previous_entry_ts:
        previous_timestamp = previous_entry_ts.timestamp
        timestamp = linearize_timestamp(timestamp, previous_timestamp)
    else:
        timestamp = timestamp

    previous_entry = Timestamp.query.filter_by(anchor_id=anchor_id, frame_type=frame_type).order_by(Timestamp.id.desc()).first()

    if previous_entry:
        previous_sequence_number = previous_entry.sequence_number
        sequence_number = linearize_sequence_number(sequence_number, previous_sequence_number)
    else:
        sequence_number = sequence_number

    new_timestamp = Timestamp(anchor_id=anchor_id, timestamp=timestamp, frame_type=frame_type, sequence_number=sequence_number)
    db.session.add(new_timestamp)
    db.session.commit()
    
    if frame_type == 'sync':
        sync_timestamps = Timestamp.query.filter_by(anchor_id=anchor_id, frame_type='sync').order_by(Timestamp.id.desc()).limit(2).all()
        update_clock_model(anchor_id, sync_timestamps)

    if frame_type == 'tag':
        calculate_position_if_all_anchors_received(sequence_number)

    return jsonify({'message': 'Timestamp received'}), 200

def calculate_position_if_all_anchors_received(sequence_number):
    tag_timestamps = Timestamp.query.filter_by(frame_type='tag', sequence_number=sequence_number).all()
    if len(tag_timestamps) < len(anchor_positions):
        return

    timestamps_dict = {t.anchor_id: t.timestamp for t in tag_timestamps}
    calculate_and_send_position(sequence_number, timestamps_dict)

def calculate_and_send_position(sequence_number, timestamps_dict):
    tag_timestamps = timestamps_dict
    data = {
        "tag_id": "tag",
        "timestamps": tag_timestamps,
        "sequence_number": sequence_number
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

def linearize_sequence_number(current_seq, previous_seq, rollover_limit=256):
    if current_seq < previous_seq:
        rollover_count = (previous_seq - current_seq) // rollover_limit + 1
        return current_seq + rollover_limit * rollover_count
    return current_seq

def linearize_timestamp(timestamp, prev_timestamp, rollover_limit=(1 << 40)):
    if timestamp < prev_timestamp:
        rollover_count = (prev_timestamp - timestamp) // rollover_limit + 1
        adjusted_timestamp = timestamp + rollover_limit * rollover_count
        return adjusted_timestamp
    else:
        return timestamp

def update_clock_model(anchor_id, sync_timestamps):
    if len(sync_timestamps) < 2:
        app.logger.debug(f"Not enough sync timestamps to update clock model for anchor {anchor_id}")
        return

    ts_n_k = sync_timestamps[0]
    ts_n_k_minus_1 = sync_timestamps[1]
    
    k = ts_n_k.sequence_number
    k_minus_1 = ts_n_k_minus_1.sequence_number
    
    tau_s = int(0.2 / TIMESTAMP_CONVERSION_FACTOR) # sec

    delta_k = k - k_minus_1
    tr_k = k * tau_s
    tr_k_minus_1 = k_minus_1 * tau_s

    E_n_k = ts_n_k.timestamp - tr_k
    E_n_k_minus_1 = ts_n_k_minus_1.timestamp  - tr_k_minus_1
    
    i_n_k = (E_n_k - E_n_k_minus_1) / (delta_k * tau_s)

    clock_model = ClockModel.query.filter_by(anchor_id=anchor_id).first()
    if clock_model is None:
        clock_model = ClockModel(anchor_id=anchor_id, offset=E_n_k, drift=i_n_k)
    else:
        clock_model.offset = E_n_k
        clock_model.drift = i_n_k

    db.session.add(clock_model)
    db.session.commit()

def calculate_positioning_timestamp(anchor_id, tag_timestamp, sync_timestamps):
    clock_model = ClockModel.query.filter_by(anchor_id=anchor_id).first()
    if clock_model is None:
        app.logger.debug(f"No clock model found for anchor {anchor_id}, returning original timestamp")
        return tag_timestamp.timestamp

    ts_n_k = sync_timestamps[0]

    E_n_i = clock_model.offset + clock_model.drift * (tag_timestamp.timestamp - ts_n_k.timestamp)

    corrected_timestamp = tag_timestamp.timestamp - E_n_i
    app.logger.debug(f"Calculated corrected timestamp for anchor {anchor_id}: {corrected_timestamp}")

    return corrected_timestamp

def plot_all_positions():
    positions = TagPosition.query.all()

    plt.figure(figsize=(5, 5))

    # 태그 위치들을 빨간 점으로 표시
    for position in positions:
        plt.plot(position.x, position.y, 'ro')

    # 앵커 위치를 파란 점으로 표시
    anchor_x = [pos[0] for pos in anchor_positions]
    anchor_y = [pos[1] for pos in anchor_positions]
    plt.plot(anchor_x, anchor_y, 'bo')  

    plt.xlim(-1, 4)  
    plt.ylim(-1, 3)  
    plt.xlabel('X Position (m)')
    plt.ylabel('Y Position (m)')
    plt.title('Tag Positions')

    img = io.BytesIO()
    plt.savefig(img, format='png')
    img.seek(0)
    plot_url = base64.b64encode(img.getvalue()).decode('utf8')
    plt.close()

    return plot_url

@app.route('/positions')
def show_all_positions():
    plot_url = plot_all_positions()
    return render_template('positions.html', plot_url=plot_url)

@app.route('/api/calculate_position', methods=['POST'])
def calculate_position():
    tag_data = request.get_json()

    if not tag_data or not isinstance(tag_data.get('timestamps'), dict):
        app.logger.error("Invalid data provided")
        return jsonify({'message': 'Invalid data provided'}), 400

    tag_timestamps = tag_data.get('timestamps')
    tag_id = tag_data.get('tag_id')

    # Anchor ID의 수에 맞게 리스트 초기화
    corrected_timestamps = [None] * len(anchor_id_map)

    for anchor_id, ts in tag_timestamps.items():
        tag_timestamp = Timestamp.query.filter_by(anchor_id=anchor_id, frame_type='tag').order_by(Timestamp.id.desc()).first()
        if tag_timestamp is None:
            app.logger.error(f"Timestamp for anchor {anchor_id} with timestamp {ts} not found")
            return jsonify({'message': f'Timestamp for anchor {anchor_id} not found'}), 404
        
        sync_timestamps = Timestamp.query.filter_by(anchor_id=anchor_id, frame_type='sync').order_by(Timestamp.id.desc()).limit(2).all()

        corrected_timestamp = calculate_positioning_timestamp(anchor_id, tag_timestamp, sync_timestamps)

        # 올바른 인덱스에 저장
        anchor_index = anchor_id_map.get(anchor_id)
        if anchor_index is not None and 0 <= anchor_index < len(corrected_timestamps):
            corrected_timestamps[anchor_index] = corrected_timestamp
        else:
            app.logger.error(f"Invalid anchor index {anchor_index} for anchor_id {anchor_id}")
            return jsonify({'message': f'Invalid anchor index for anchor_id {anchor_id}'}), 400
        
        if not np.isfinite(corrected_timestamp):
            app.logger.error(f"Corrected timestamp for anchor {anchor_id} is not finite: {corrected_timestamp}")
            return jsonify({'message': f'Corrected timestamp for anchor {anchor_id} is not finite'}), 400

    # check if all timestamps were filled
    if None in corrected_timestamps:
        app.logger.error("Not all anchors have provided timestamps")
        return jsonify({'message': 'Missing timestamps for some anchors'}), 400

    estimated_position = estimate_position(corrected_timestamps)
    x, y = estimated_position.tolist()
    
    app.logger.debug(f"Estimated Position: x={x}, y={y}")


    new_tag_position = TagPosition(tag_id=tag_id, x=x, y=y, timestamp=int(datetime.datetime.now().timestamp()))
    db.session.add(new_tag_position)
    db.session.commit()

    return jsonify({'estimated_position': [x, y]}), 200

def h(si, corrected_timestamps):
    t1_i = corrected_timestamps[0]
    c = 299792458  # 빛의 속도 (m/s)
    h_vec = []

    for n in range(1, len(corrected_timestamps)):
        tn_i = corrected_timestamps[n]
        diff = (tn_i - t1_i) * TIMESTAMP_CONVERSION_FACTOR
        # print(diff)
        # app.logger.debug(f"tn_i  anchor {n+1}: {tn_i}")
        # app.logger.debug(f"t1_i for anchor {n+1}: {t1_i}")
        # app.logger.debug(f"Time difference (tn_i - t1_i) for anchor {n+1}: {tn_i - t1_i}")
        # app.logger.debug(f"distance {n+1}: {c*diff}")
        h_vec.append(c * diff )

    # app.logger.debug(f"h vector: {h_vec}")
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

    return H

def ekf_update(si, corrected_timestamps):
    H = jacobian(si, corrected_timestamps)
    h_si = h(si, corrected_timestamps)
    
    residual = h_si - np.dot(H, si)
    return residual

def estimate_position(corrected_timestamps):
    initial_guess = [1.5,2]
    result = least_squares(ekf_update, initial_guess, args=(corrected_timestamps,))

    return result.x


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
