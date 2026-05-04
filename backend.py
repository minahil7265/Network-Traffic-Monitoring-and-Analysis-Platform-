from flask import Flask, render_template, request
from scapy.all import sniff, IP, TCP, UDP, ICMP
import threading
import csv
from datetime import datetime
import signal
import sys

app = Flask(__name__)

live_data = []
csv_data = []
monitoring = False
stop_sniffing_flag = False
data_lock = threading.Lock()

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

def check_permissions():
    import os
    if os.name == 'posix' and os.geteuid() != 0:
        print("⚠️ Warning: Run with sudo for packet sniffing!")

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
        21: "FTP",
        25: "SMTP",
        3306: "MySQL",
        5432: "PostgreSQL",
        6379: "Redis",
        27017: "MongoDB",
        3389: "RDP",
        143: "IMAP",
        993: "IMAPS",
        8080: "HTTP-Alt",
        8443: "HTTPS-Alt",
    }
    return services.get(port, "Other")

def process_packet(packet):
    global live_data
    
    with data_lock:
        if packet.haslayer(IP):
            proto = "OTHER"
            src_port = 0
            dst_port = 0
            
            if packet.haslayer(TCP):
                proto = "TCP"
                src_port = packet[TCP].sport
                dst_port = packet[TCP].dport
            elif packet.haslayer(UDP):
                proto = "UDP"
                src_port = packet[UDP].sport
                dst_port = packet[UDP].dport
            elif packet.haslayer(ICMP):
                proto = "ICMP"

            src = packet[IP].src
            dst = packet[IP].dst
            size = len(packet)

            live_data.append({
                "time": datetime.now().strftime("%H:%M:%S"),
                "src_ip": src,
                "src_port": src_port,
                "dest_ip": dst,
                "dest_port": dst_port,
                "protocol": proto,
                "packet_size": size,
                "port": dst_port
            })

            if len(live_data) > 200:
                live_data.pop(0)

def start_sniffing():
    global stop_sniffing_flag
    sniff(prn=process_packet, store=False, stop_filter=lambda x: stop_sniffing_flag)

def signal_handler(sig, frame):
    global monitoring, stop_sniffing_flag
    print("\n🛑 Shutting down gracefully...")
    monitoring = False
    stop_sniffing_flag = True
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

@app.route('/', methods=['GET', 'POST'])
def index():
    global monitoring, stop_sniffing_flag

    with data_lock:
        data = csv_data + live_data
    filtered = data.copy()

    if request.method == 'POST':
        if 'start' in request.form and not monitoring:
            monitoring = True
            stop_sniffing_flag = False
            t = threading.Thread(target=start_sniffing, daemon=True)
            t.start()
            print("✅ Monitoring Started")

        elif 'stop' in request.form:
            monitoring = False
            stop_sniffing_flag = True
            print("⏹️ Monitoring Stopped")

        elif 'filter' in request.form:
            protocol = request.form.get('protocol', '').upper()
            src = request.form.get('src_ip', '')
            dst = request.form.get('dest_ip', '')
            src_port = request.form.get('src_port', '')
            dst_port = request.form.get('dst_port', '')
            service = request.form.get('service', '')

            if protocol:
                filtered = [d for d in filtered if d['protocol'] == protocol]
            if src:
                filtered = [d for d in filtered if src in d['src_ip']]
            if dst:
                filtered = [d for d in filtered if dst in d['dest_ip']]
            if src_port:
                try:
                    src_port_int = int(src_port)
                    filtered = [d for d in filtered if d.get('src_port', 0) == src_port_int]
                except:
                    pass
            if dst_port:
                try:
                    dst_port_int = int(dst_port)
                    filtered = [d for d in filtered if d.get('dest_port', 0) == dst_port_int]
                except:
                    pass
            if service:
                filtered = [d for d in filtered if get_service(d.get('dest_port', d.get('port', 0))) == service]

        elif 'reset' in request.form:
            filtered = data.copy()

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

if __name__ == '__main__':
    load_csv()
    check_permissions()
    print("🚀 Server running at http://127.0.0.1:5000")
    app.run(debug=True, host='127.0.0.1', port=5000)