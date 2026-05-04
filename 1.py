from flask import Flask, render_template, request
from scapy.all import sniff, IP, TCP, UDP, ICMP
import threading
import csv
from datetime import datetime

app = Flask(__name__)

# ---------------- DATA ----------------
live_data = []
csv_data = []
monitoring = False
stop_sniffing_flag = False  # Added

# ---------------- LOAD CSV ----------------
def load_csv():
    global csv_data
    csv_data = []
    
    try:
        with open('data.csv', 'r') as file:
            reader = csv.DictReader(file)
            for row in reader:
                row['packet_size'] = row.get('size', 0)
                csv_data.append(row)
    except FileNotFoundError:
        print("data.csv not found, starting with empty data")
    except Exception as e:
        print(f"Error loading CSV: {e}")

# ---------------- PERMISSIONS CHECK ----------------
def check_permissions():
    import os
    if os.name == 'posix' and os.geteuid() != 0:
        print("⚠️ Warning: Run with sudo for packet sniffing!")

# ---------------- SERVICE MAP ----------------
def get_service(port):
    try:
        port = int(port)
    except:
        return "Other"

    services = {
        80: "HTTP",
        443: "HTTPS",
        53: "DNS",
        22: "SSH",
        21: "FTP"
    }
    return services.get(port, "Other")

# ---------------- PACKET HANDLER ----------------
def process_packet(packet):
    global live_data

    if packet.haslayer(IP):
        proto = "OTHER"
        if packet.haslayer(TCP):
            proto = "TCP"
        elif packet.haslayer(UDP):
            proto = "UDP"
        elif packet.haslayer(ICMP):
            proto = "ICMP"

        src = packet[IP].src
        dst = packet[IP].dst
        size = len(packet)

        port = 0
        if packet.haslayer(TCP):
            port = packet[TCP].dport
        elif packet.haslayer(UDP):
            port = packet[UDP].dport

        live_data.append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "src_ip": src,
            "dest_ip": dst,
            "protocol": proto,
            "packet_size": size,
            "port": port
        })

        if len(live_data) > 200:
            live_data.pop(0)

# ---------------- SNIFFER THREAD ----------------
def start_sniffing():
    global stop_sniffing_flag
    sniff(prn=process_packet, store=False, stop_filter=lambda x: stop_sniffing_flag)

# ---------------- ROUTE ----------------
@app.route('/', methods=['GET', 'POST'])
def index():
    global monitoring, stop_sniffing_flag

    data = csv_data + live_data
    filtered = data.copy()

    if request.method == 'POST':
        if 'start' in request.form and not monitoring:
            monitoring = True
            stop_sniffing_flag = False  # Reset flag
            t = threading.Thread(target=start_sniffing, daemon=True)
            t.start()

        elif 'stop' in request.form:
            monitoring = False
            stop_sniffing_flag = True  # Stop sniffing

        elif 'filter' in request.form:
            protocol = request.form.get('protocol', '').upper()
            src = request.form.get('src_ip', '')
            dst = request.form.get('dest_ip', '')

            if protocol:
                filtered = [d for d in filtered if d['protocol'] == protocol]
            if src:
                filtered = [d for d in filtered if src in d['src_ip']]
            if dst:
                filtered = [d for d in filtered if dst in d['dest_ip']]

        elif 'reset' in request.form:
            filtered = data.copy()

    # ---------------- STATS ----------------
    total = len(filtered)
    tcp = len([d for d in filtered if d['protocol'] == 'TCP'])
    udp = len([d for d in filtered if d['protocol'] == 'UDP'])
    icmp = len([d for d in filtered if d['protocol'] == 'ICMP'])

    avg_size = 0
    if total > 0:
        avg_size = sum(int(d['packet_size']) for d in filtered) / total

    return render_template(
        'index.html',
        data=filtered,
        service=get_service,
        total=total,
        tcp=tcp,
        udp=udp,
        icmp=icmp,
        avg_size=round(avg_size, 2),
        monitoring=monitoring
    )

# ---------------- RUN ----------------
if __name__ == '__main__':
    load_csv()
    check_permissions()  # Call permission check
    app.run(debug=True)