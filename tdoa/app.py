from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
import datetime

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tdoa.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class Timestamp(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    anchor_id = db.Column(db.String(50))
    timestamp = db.Column(db.BigInteger)
    frame_type = db.Column(db.String(50))  # 'sync' or 'tag'
    sequence_number = db.Column(db.Integer)
    received_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class ClockModel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    anchor_id = db.Column(db.String(50), unique=True)
    offset = db.Column(db.Float)
    drift = db.Column(db.Float)

with app.app_context():
    db.create_all()

@app.route('/api/timestamps', methods=['POST'])
def receive_timestamp():
    data = request.get_json()
    anchor_id = data.get('anchor_id')
    timestamp = data.get('timestamp')
    frame_type = data.get('frame_type')  # 'sync' or 'tag'
    sequence_number = data.get('sequence_number')

    new_timestamp = Timestamp(anchor_id=anchor_id, timestamp=timestamp, frame_type=frame_type, sequence_number=sequence_number)
    db.session.add(new_timestamp)
    db.session.commit()

    if frame_type == 'sync':
        sync_timestamps = Timestamp.query.filter_by(anchor_id=anchor_id, frame_type='sync').order_by(Timestamp.sequence_number).all()
        update_clock_model(anchor_id, sync_timestamps)

    return jsonify({'message': 'Timestamp received'}), 200

def update_clock_model(anchor_id, sync_timestamps):
    if len(sync_timestamps) < 2:
        return  # 최소 두 개의 동기화 타임스탬프가 필요합니다

    ts_n_k = sync_timestamps[-1]
    ts_n_k_minus_1 = sync_timestamps[-2]

    tr_k = ts_n_k.sequence_number * 100

    E_n_k = ts_n_k.timestamp - tr_k
    E_n_k_minus_1 = ts_n_k_minus_1.timestamp - (ts_n_k_minus_1.sequence_number * 100)

    i_n_k = (E_n_k - E_n_k_minus_1) / 100

    clock_model = ClockModel.query.filter_by(anchor_id=anchor_id).first()
    if clock_model is None:
        clock_model = ClockModel(anchor_id=anchor_id, offset=E_n_k, drift=i_n_k)
    else:
        clock_model.offset = E_n_k
        clock_model.drift = i_n_k

    db.session.add(clock_model)
    db.session.commit()

def calculate_positioning_timestamp(anchor_id, tag_timestamp):
    clock_model = ClockModel.query.filter_by(anchor_id=anchor_id).first()
    if clock_model is None:
        return tag_timestamp.timestamp

    E_n_i = clock_model.offset + clock_model.drift * (tag_timestamp.timestamp - tag_timestamp.received_at.timestamp())

    corrected_timestamp = tag_timestamp.timestamp - E_n_i
    return corrected_timestamp

@app.route('/api/calculate_position', methods=['POST'])
def calculate_position():
    tag_data = request.get_json()
    tag_timestamps = tag_data.get('timestamps')

    corrected_timestamps = {}
    for anchor_id, ts in tag_timestamps.items():
        tag_timestamp = Timestamp.query.filter_by(anchor_id=anchor_id, frame_type='tag', timestamp=ts).first()
        corrected_timestamps[anchor_id] = calculate_positioning_timestamp(anchor_id, tag_timestamp)

    return jsonify(corrected_timestamps), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)